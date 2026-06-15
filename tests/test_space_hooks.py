import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from small_cuts.space_hooks import (
    RELAY_HOOK_TOKEN_ENV,
    RelayEventHub,
    install_relay_hooks,
    relay_event_stream,
)


def test_relay_event_hub_broadcasts_to_subscribers():
    async def scenario():
        hub = RelayEventHub()
        queue = hub.subscribe()

        event = await hub.publish({"scene_id": "scene-1"})
        seen = await asyncio.wait_for(queue.get(), timeout=0.1)

        assert event["id"] == 1
        assert seen["payload"]["scene_id"] == "scene-1"

    asyncio.run(scenario())


def test_relay_hook_requires_configured_token(monkeypatch):
    app = FastAPI()
    install_relay_hooks(app, hub=RelayEventHub())
    client = TestClient(app)

    response = client.post("/small-cuts/hooks/relay-scene", json={"scene_id": "scene-1"})

    assert response.status_code == 503
    assert response.json()["detail"] == "relay hook is not configured"

    monkeypatch.setenv(RELAY_HOOK_TOKEN_ENV, "secret")
    response = client.post("/small-cuts/hooks/relay-scene", json={"scene_id": "scene-1"})

    assert response.status_code == 401


def test_relay_hook_accepts_bearer_and_publishes(monkeypatch):
    monkeypatch.setenv(RELAY_HOOK_TOKEN_ENV, "secret")
    hub = RelayEventHub()
    app = FastAPI()
    install_relay_hooks(app, hub=hub)
    client = TestClient(app)

    response = client.post(
        "/small-cuts/hooks/relay-scene",
        headers={"authorization": "Bearer secret"},
        json={"scene_id": "scene-1"},
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted", "event_id": 1}


def test_relay_event_stream_sends_idle_ping_and_unsubscribes():
    class Request:
        async def is_disconnected(self):
            return False

    async def scenario():
        hub = RelayEventHub()
        stream = relay_event_stream(hub, Request(), heartbeat_s=0.01)

        assert await anext(stream) == 'event: ready\ndata: {"status":"connected"}\n\n'
        assert await anext(stream) == ": ping\n\n"
        await stream.aclose()

        assert len(hub._subscribers) == 0

    asyncio.run(scenario())
