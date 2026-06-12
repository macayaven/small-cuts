"""App factory for the home-node narration engine (Team Inference)."""

from __future__ import annotations

from fastapi import FastAPI, WebSocket

from .session import EngineState, SceneSink, SessionRunner


def build_engine_app(scene_sink: SceneSink | None = None) -> FastAPI:
    """One WebSocket per wearing session (`/v1/session`), per docs/contracts."""
    state = EngineState(sink=scene_sink) if scene_sink is not None else EngineState()
    app = FastAPI(title="small-cuts engine")

    @app.websocket("/v1/session")
    async def session(websocket: WebSocket) -> None:
        await websocket.accept()
        await SessionRunner(websocket, state).run()

    return app
