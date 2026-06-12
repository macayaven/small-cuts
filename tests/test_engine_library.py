"""Scene library + viewer-facing API: storage, SSE stream, visibility (D6/D7).

Runs entirely on the mock narrator/TTS backends — deterministic, no weights.
"""

import asyncio
import io
import json
import uuid
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

fastapi = pytest.importorskip("fastapi")
jsonschema = pytest.importorskip("jsonschema")

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from small_cuts.engine import build_engine_app  # noqa: E402
from small_cuts.engine.app import _last_event_id, scene_event_stream  # noqa: E402
from small_cuts.engine.library import SceneLibrary  # noqa: E402
from small_cuts.title_card import derive_title  # noqa: E402
from test_engine_session import Reader, make_envelope  # noqa: E402

CONTRACTS = Path(__file__).parent.parent / "docs" / "contracts"
NARRATED_SCENE_SCHEMA = json.loads((CONTRACTS / "narrated-scene.schema.json").read_text())


@pytest.fixture(autouse=True)
def engine_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SMALL_CUTS_BACKEND", "mock")
    monkeypatch.setenv("SMALL_CUTS_TTS_BACKEND", "mock")
    monkeypatch.setenv("SMALL_CUTS_LIBRARY_DIR", str(tmp_path / "library-env"))


def make_sink_scene(**overrides) -> dict:
    """The dict the session hands to its SceneSink after a successful narration."""
    now = datetime.now(timezone.utc)
    scene = {
        "scene_id": str(uuid.uuid4()),
        "moment_id": str(uuid.uuid4()),
        "session_id": "2026-06-12-morning-walk",
        "captured_at": now.isoformat(),
        "created_at": (now + timedelta(seconds=2)).isoformat(),
        "style_key": "noir",
        "narration": "The corridor kept its opinions to itself. Nobody asked twice.",
        "image": Image.new("RGB", (16, 16), (12, 24, 48)),
        "audio": np.zeros(240, dtype=np.float32),
        "sample_rate": 24_000,
        "latency_ms": {"queue": 1, "narration": 2, "tts": 3, "total": 6},
    }
    scene.update(overrides)
    return scene


def parse_sse(event: str) -> tuple[int, dict]:
    """`id: <seq>\\ndata: <json>\\n\\n` -> (id, NarratedScene)."""
    id_line, data_line = event.rstrip("\n").split("\n", 1)
    return int(id_line.removeprefix("id: ")), json.loads(data_line.removeprefix("data: "))


# -- full WS -> sink -> storage flow ------------------------------------------


def test_ws_flow_persists_contract_valid_scene(tmp_path):
    lib = SceneLibrary(tmp_path / "lib")
    envelope = make_envelope()
    with TestClient(build_engine_app(library=lib)) as client:
        with client.websocket_connect("/v1/session") as ws:
            reader = Reader(ws)
            ws.send_text(json.dumps(envelope))
            audio_frame = reader.next_scene_audio()
            # The final idle status is emitted after the sink ran: storage is done.
            reader.next(lambda f: f.get("kind") == "status" and f["status"]["busy"] is False)

        listed = client.get("/v1/scenes").json()["scenes"]
        assert len(listed) == 1
        scene = listed[0]
        jsonschema.validate(scene, NARRATED_SCENE_SCHEMA)
        assert scene["scene_id"] == audio_frame["scene_id"]
        assert scene["moment_id"] == envelope["moment_id"]
        assert scene["session_id"] == envelope["session_id"]
        assert scene["captured_at"] == envelope["captured_at"]
        assert scene["created_at"] == audio_frame["created_at"]
        assert scene["style_key"] == envelope["context"]["style_key"]
        assert scene["narration"] == audio_frame["narration"]
        assert scene["title"] == derive_title(scene["narration"])
        assert scene["visibility"] == "private"
        assert scene["seq"] == 0
        assert scene["owner"] == "carlos"
        engine = scene["engine"]
        assert engine["narrator_backend"] == "mock"
        assert engine["narrator_model"] == "mock-narrator-0"
        assert engine["tts_model"] == "mock-tts-0"
        assert all(v >= 0 for v in engine["latency_ms"].values())

        media_dir = tmp_path / "lib" / "media" / scene["scene_id"]
        for name in ("frame.jpg", "card.webp", "voice.wav"):
            assert (media_dir / name).is_file()

        frame = client.get(scene["media"]["frame_url"])
        assert frame.status_code == 200
        assert frame.content == (media_dir / "frame.jpg").read_bytes()
        assert Image.open(io.BytesIO(frame.content)).format == "JPEG"

        card = client.get(scene["media"]["card_url"])
        assert card.status_code == 200
        assert Image.open(io.BytesIO(card.content)).format == "WEBP"

        voice = client.get(scene["media"]["audio_url"])
        assert voice.status_code == 200
        with wave.open(io.BytesIO(voice.content)) as wav:
            assert wav.getframerate() == audio_frame["sample_rate"]
            assert wav.getnframes() > 0


# -- library storage ------------------------------------------------------------


def test_seq_monotonic_across_scenes_and_reopen(tmp_path):
    root = tmp_path / "lib"
    lib = SceneLibrary(root)
    first = lib.store(make_sink_scene())
    second = lib.store(make_sink_scene())
    assert (first["seq"], second["seq"]) == (0, 1)
    lib.close()

    reopened = SceneLibrary(root)  # seq survives a restart: resume ids stay valid
    assert reopened.store(make_sink_scene())["seq"] == 2


def test_get_scene(tmp_path):
    lib = SceneLibrary(tmp_path / "lib")
    stored = lib.store(make_sink_scene())
    jsonschema.validate(stored, NARRATED_SCENE_SCHEMA)
    assert lib.get(stored["scene_id"]) == stored
    assert lib.get(str(uuid.uuid4())) is None


def test_library_root_from_env(tmp_path):
    lib = SceneLibrary()  # engine_env fixture points SMALL_CUTS_LIBRARY_DIR at tmp_path
    assert lib.root == (tmp_path / "library-env").resolve()
    assert (lib.root / "library.sqlite3").is_file()


def test_set_visibility_rejects_unknown_value(tmp_path):
    lib = SceneLibrary(tmp_path / "lib")
    stored = lib.store(make_sink_scene())
    with pytest.raises(ValueError):
        lib.set_visibility(stored["scene_id"], "secret")


# -- list + filters ---------------------------------------------------------------


def test_list_scenes_filters_and_order(tmp_path):
    lib = SceneLibrary(tmp_path / "lib")
    base = datetime(2026, 6, 12, 9, 0, tzinfo=timezone.utc)

    def at(minutes: int) -> str:
        return (base + timedelta(minutes=minutes)).isoformat()

    for minutes in (2, 0, 1):  # arrival order is not chronology (D8/D9)
        lib.store(make_sink_scene(session_id="walk", captured_at=at(minutes)))
    lunch = lib.store(make_sink_scene(session_id="lunch", captured_at=at(9)))
    lib.set_visibility(lunch["scene_id"], "public")

    with TestClient(build_engine_app(library=lib)) as client:
        scenes = client.get("/v1/scenes").json()["scenes"]
        assert [s["captured_at"] for s in scenes] == [at(0), at(1), at(2), at(9)]

        walk = client.get("/v1/scenes", params={"session": "walk"}).json()["scenes"]
        assert len(walk) == 3 and {s["session_id"] for s in walk} == {"walk"}

        public = client.get("/v1/scenes", params={"visibility": "public"}).json()["scenes"]
        assert [s["scene_id"] for s in public] == [lunch["scene_id"]]

        limited = client.get("/v1/scenes", params={"limit": 2}).json()["scenes"]
        assert [s["captured_at"] for s in limited] == [at(0), at(1)]

        assert client.get("/v1/scenes", params={"visibility": "secret"}).status_code == 422


# -- visibility mutations -----------------------------------------------------------


def test_patch_visibility_round_trip(tmp_path):
    lib = SceneLibrary(tmp_path / "lib")
    stored = lib.store(make_sink_scene())
    with TestClient(build_engine_app(library=lib)) as client:
        response = client.patch(f"/v1/scenes/{stored['scene_id']}", json={"visibility": "shared"})
        assert response.status_code == 200
        updated = response.json()
        jsonschema.validate(updated, NARRATED_SCENE_SCHEMA)
        assert updated["visibility"] == "shared"
        assert updated["scene_id"] == stored["scene_id"]
        assert client.get("/v1/scenes").json()["scenes"][0]["visibility"] == "shared"


def test_patch_unknown_scene_404(tmp_path):
    with TestClient(build_engine_app(library=SceneLibrary(tmp_path / "lib"))) as client:
        response = client.patch(f"/v1/scenes/{uuid.uuid4()}", json={"visibility": "public"})
        assert response.status_code == 404


def test_patch_invalid_visibility_422(tmp_path):
    lib = SceneLibrary(tmp_path / "lib")
    stored = lib.store(make_sink_scene())
    with TestClient(build_engine_app(library=lib)) as client:
        response = client.patch(f"/v1/scenes/{stored['scene_id']}", json={"visibility": "secret"})
        assert response.status_code == 422
        assert lib.get(stored["scene_id"])["visibility"] == "private"


# -- SSE stream -------------------------------------------------------------------


def test_sse_live_event_id_matches_seq(tmp_path):
    async def run():
        lib = SceneLibrary(tmp_path / "lib")
        stream = scene_event_stream(lib, last_event_id=None, heartbeat_s=30.0)
        first = asyncio.ensure_future(anext(stream))
        await asyncio.sleep(0)  # let the stream subscribe before the scene lands
        await lib(make_sink_scene())  # the real sink path: store, then publish
        event = await asyncio.wait_for(first, timeout=10)
        await stream.aclose()
        assert lib._subscribers == []  # unsubscribed on close
        return event

    event_id, payload = parse_sse(asyncio.run(run()))
    assert event_id == 0
    jsonschema.validate(payload, NARRATED_SCENE_SCHEMA)
    assert payload["seq"] == 0


def test_sse_resume_replays_missed_scenes_then_goes_live(tmp_path):
    # TestClient buffers whole response bodies, so an endless SSE stream cannot be
    # consumed over HTTP in tests; driving the stream generator directly is the
    # same code path minus the transport.
    async def run():
        lib = SceneLibrary(tmp_path / "lib")
        stored = [lib.store(make_sink_scene()) for _ in range(3)]
        stream = scene_event_stream(lib, last_event_id=0, heartbeat_s=30.0)
        replayed = [await asyncio.wait_for(anext(stream), timeout=10) for _ in range(2)]
        await lib(make_sink_scene())  # the same connection then receives live scenes
        live = await asyncio.wait_for(anext(stream), timeout=10)
        await stream.aclose()
        return stored, replayed, live

    stored, replayed, live = asyncio.run(run())
    assert [parse_sse(event)[0] for event in replayed] == [1, 2]
    assert [parse_sse(event)[1]["scene_id"] for event in replayed] == [
        scene["scene_id"] for scene in stored[1:]
    ]
    live_id, live_scene = parse_sse(live)
    assert live_id == 3
    jsonschema.validate(live_scene, NARRATED_SCENE_SCHEMA)


def test_last_event_id_header_parsing():
    assert _last_event_id(None) is None
    assert _last_event_id("412") == 412
    assert _last_event_id("not-a-seq") is None


def test_sse_heartbeat_comment_when_idle(tmp_path):
    async def run():
        lib = SceneLibrary(tmp_path / "lib")
        stream = scene_event_stream(lib, last_event_id=None, heartbeat_s=0.01)
        event = await asyncio.wait_for(anext(stream), timeout=10)
        await stream.aclose()
        return event

    assert asyncio.run(run()) == ": ping\n\n"


# -- media routes ---------------------------------------------------------------


def test_media_unknown_filename_and_scene_404(tmp_path):
    lib = SceneLibrary(tmp_path / "lib")
    stored = lib.store(make_sink_scene())
    with TestClient(build_engine_app(library=lib)) as client:
        assert client.get(f"/media/{stored['scene_id']}/library.sqlite3").status_code == 404
        assert client.get(f"/media/{uuid.uuid4()}/frame.jpg").status_code == 404


def test_media_path_traversal_rejected(tmp_path):
    lib = SceneLibrary(tmp_path / "lib")
    stored = lib.store(make_sink_scene())
    (lib.root / "frame.jpg").write_bytes(b"outside media")  # decoy outside media/

    # The guard itself: whitelist filenames, resolved path stays inside media/.
    assert lib.media_path(stored["scene_id"], "frame.jpg") is not None
    assert lib.media_path(stored["scene_id"], "../library.sqlite3") is None
    assert lib.media_path("..", "frame.jpg") is None
    assert lib.media_path(f"../{lib.root.name}", "frame.jpg") is None

    with TestClient(build_engine_app(library=lib)) as client:
        assert client.get("/media/%2E%2E/frame.jpg").status_code == 404
        assert client.get(f"/media/{stored['scene_id']}/..%2Flibrary.sqlite3").status_code == 404
