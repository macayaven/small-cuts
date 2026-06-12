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


def _sse_event(event: dict[str, Any]) -> str:
    data = f"data: {json.dumps(event)}\n\n"
    seq = event.get("seq")
    # No seq -> ephemeral event (error frames): no id line, so it never becomes
    # a Last-Event-ID resume cursor and is never expected in replay.
    return data if seq is None else f"id: {seq}\n{data}"


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
    """SSE body: replay seq > Last-Event-ID, then live events; pings while idle.

    Live events without a seq (pipeline errors) pass straight through —
    they are ephemeral and never part of replay.
    """
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
                event = await asyncio.wait_for(queue.get(), timeout=heartbeat_s)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            # Invariant: the library publishes each seq exactly once, so live
            # events never need dedupe against each other. `last_seq` stays
            # frozen at the replay boundary — it only filters scenes that were
            # both replayed and queued (stored before replay, published after
            # subscribe). It must NOT advance here: store() commits seq under
            # the lock in a worker thread but publishes later on the loop, so
            # concurrent sessions can publish out of seq order, and a moving
            # cursor would drop the lower seq forever.
            seq = event.get("seq")
            if seq is not None and seq <= last_seq:
                continue
            yield _sse_event(event)
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
    sink = scene_sink if scene_sink is not None else lib
    # Errors fan out to the viewer stream too (D9): the timeline shows failures.
    state = EngineState(sink=sink, error_sink=lib.publish_event)
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
