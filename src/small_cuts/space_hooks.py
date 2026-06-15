"""Push hooks for relay-scene updates in the Gradio Space.

The Space should not poll Hugging Face control-plane APIs or repeatedly poll the
relay bucket. The local publisher calls the protected hook after it writes a new
manifest; browser clients keep one SSE connection open and refresh once per
hook event.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

RELAY_HOOK_TOKEN_ENV = "SMALL_CUTS_RELAY_HOOK_TOKEN"
RELAY_HOOK_PATH = "/small-cuts/hooks/relay-scene"
RELAY_EVENTS_PATH = "/small-cuts/events"
SSE_HEARTBEAT_S = 15.0


class RelayEventHub:
    def __init__(self) -> None:
        self._next_id = 0
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=8)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    async def publish(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._next_id += 1
        event = {"id": self._next_id, "payload": payload or {}}
        stale: list[asyncio.Queue[dict[str, Any]]] = []
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                stale.append(queue)
        for queue in stale:
            self.unsubscribe(queue)
        return event


def install_relay_hooks(app: FastAPI, *, hub: RelayEventHub | None = None) -> RelayEventHub:
    if getattr(app.state, "small_cuts_relay_hooks_installed", False):
        return app.state.small_cuts_relay_event_hub

    event_hub = hub or RelayEventHub()
    app.state.small_cuts_relay_hooks_installed = True
    app.state.small_cuts_relay_event_hub = event_hub

    @app.post(RELAY_HOOK_PATH, status_code=202)
    async def relay_scene_hook(
        payload: Annotated[dict[str, Any] | None, Body()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        _require_hook_authorization(authorization)
        event = await event_hub.publish(payload or {})
        return {"status": "accepted", "event_id": event["id"]}

    @app.get(RELAY_EVENTS_PATH)
    async def relay_events(request: Request) -> StreamingResponse:
        return StreamingResponse(
            relay_event_stream(event_hub, request, heartbeat_s=SSE_HEARTBEAT_S),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return event_hub


async def relay_event_stream(
    event_hub: RelayEventHub,
    request: Request,
    *,
    heartbeat_s: float = SSE_HEARTBEAT_S,
) -> AsyncIterator[str]:
    queue = event_hub.subscribe()
    try:
        yield _sse("ready", {"status": "connected"})
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=heartbeat_s)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            yield _sse("relay-scene", event)
    finally:
        event_hub.unsubscribe(queue)


def _require_hook_authorization(authorization: str | None) -> None:
    expected = os.environ.get(RELAY_HOOK_TOKEN_ENV, "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="relay hook is not configured")
    if not authorization or not hmac.compare_digest(authorization, f"Bearer {expected}"):
        raise HTTPException(status_code=401, detail="unauthorized")


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"
