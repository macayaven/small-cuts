"""App factory for the home-node narration engine (Team Inference).

One WebSocket per wearing session (`/v1/session`), plus the viewer-facing
side of docs/contracts: the scene library REST API (D6) and the live SSE
scene stream with Last-Event-ID resume (D7).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .library import SceneLibrary
from .session import EngineState, SceneSink, SessionRunner

SSE_HEARTBEAT_S = 15.0

Visibility = Literal["private", "shared", "public"]


class VisibilityPatch(BaseModel):
    visibility: Visibility


def _sse_event(scene: dict[str, Any]) -> str:
    return f"id: {scene['seq']}\ndata: {json.dumps(scene)}\n\n"


def _last_event_id(raw: str | None) -> int | None:
    """SSE resume cursor; absent or unparsable means a fresh connect, live only."""
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def scene_event_stream(
    library: SceneLibrary, last_event_id: int | None, heartbeat_s: float
) -> AsyncIterator[str]:
    """SSE body: replay seq > Last-Event-ID, then live scenes; pings while idle."""
    queue = library.subscribe()
    try:
        last_seq = -1
        if last_event_id is not None:
            last_seq = last_event_id
            for scene in library.scenes_since(last_event_id):
                last_seq = scene["seq"]
                yield _sse_event(scene)
        while True:
            try:
                scene = await asyncio.wait_for(queue.get(), timeout=heartbeat_s)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            if scene["seq"] <= last_seq:  # stored between replay and the live loop
                continue
            last_seq = scene["seq"]
            yield _sse_event(scene)
    finally:
        library.unsubscribe(queue)


def build_engine_app(
    scene_sink: SceneSink | None = None,
    library: SceneLibrary | None = None,
    sse_heartbeat_s: float = SSE_HEARTBEAT_S,
) -> FastAPI:
    """Engine app: session socket + scene library + SSE stream, per docs/contracts.

    By default scenes are persisted to a `SceneLibrary` (root from
    `SMALL_CUTS_LIBRARY_DIR`); pass `library` to inject one, or `scene_sink`
    to replace the sink entirely (tests).
    """
    lib = library if library is not None else SceneLibrary()
    state = EngineState(sink=scene_sink) if scene_sink is not None else EngineState(sink=lib)
    app = FastAPI(title="small-cuts engine")
    app.state.library = lib

    @app.websocket("/v1/session")
    async def session(websocket: WebSocket) -> None:
        await websocket.accept()
        await SessionRunner(websocket, state).run()

    @app.get("/v1/scenes")
    def list_scenes(
        session: str | None = None,
        visibility: Visibility | None = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    ) -> dict[str, list[dict[str, Any]]]:
        return {"scenes": lib.list_scenes(session_id=session, visibility=visibility, limit=limit)}

    @app.get("/v1/scenes/stream")
    async def stream_scenes(request: Request) -> StreamingResponse:
        resume_from = _last_event_id(request.headers.get("last-event-id"))
        return StreamingResponse(
            scene_event_stream(lib, resume_from, sse_heartbeat_s),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    @app.patch("/v1/scenes/{scene_id}")
    def set_visibility(scene_id: str, patch: VisibilityPatch) -> dict[str, Any]:
        scene = lib.set_visibility(scene_id, patch.visibility)
        if scene is None:
            raise HTTPException(status_code=404, detail=f"unknown scene {scene_id}")
        return scene

    @app.get("/media/{scene_id}/{filename}")
    def media(scene_id: str, filename: str) -> FileResponse:
        path = lib.media_path(scene_id, filename)
        if path is None:  # unknown name, traversal attempt, or missing file
            raise HTTPException(status_code=404, detail="no such media")
        return FileResponse(path)

    return app
