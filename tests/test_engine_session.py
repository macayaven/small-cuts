"""Engine WebSocket session: contract-validated pipeline with D8 backpressure.

Runs entirely on the mock narrator/TTS backends — deterministic, no weights.
"""

import base64
import io
import json
import threading
import uuid
import wave
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

fastapi = pytest.importorskip("fastapi")
jsonschema = pytest.importorskip("jsonschema")

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from small_cuts.engine import build_engine_app  # noqa: E402
from small_cuts.narrator import Narration  # noqa: E402
from small_cuts.styles import DEFAULT_STYLE_KEY  # noqa: E402
from test_contracts import GOLDEN  # noqa: E402

CONTRACTS = Path(__file__).parent.parent / "docs" / "contracts"
SCENE_AUDIO_SCHEMA = json.loads((CONTRACTS / "scene-audio.schema.json").read_text())
CONTROL_SCHEMA = json.loads((CONTRACTS / "control.schema.json").read_text())

_buffer = io.BytesIO()
Image.new("RGB", (8, 8), (200, 120, 40)).save(_buffer, "JPEG")
REAL_JPEG_B64 = base64.b64encode(_buffer.getvalue()).decode()


@pytest.fixture(autouse=True)
def mock_backends(monkeypatch, tmp_path):
    monkeypatch.setenv("SMALL_CUTS_BACKEND", "mock")
    monkeypatch.setenv("SMALL_CUTS_TTS_BACKEND", "mock")
    # build_engine_app() now persists scenes to a SceneLibrary; keep it off $HOME.
    monkeypatch.setenv("SMALL_CUTS_LIBRARY_DIR", str(tmp_path / "library"))


def make_envelope(**overrides) -> dict:
    envelope = json.loads(json.dumps(GOLDEN["moment.schema.json"]))
    envelope["moment_id"] = str(uuid.uuid4())
    envelope["frames"][0]["jpeg_b64"] = REAL_JPEG_B64
    envelope.update(overrides)
    return envelope


class Reader:
    """Receives frames, validates every ControlFrame, and keeps the history."""

    def __init__(self, ws):
        self.ws = ws
        self.frames: list[dict] = []

    def next(self, predicate, limit: int = 30) -> dict:
        for _ in range(limit):
            frame = self.ws.receive_json()
            if "kind" in frame:
                jsonschema.validate(frame, CONTROL_SCHEMA)
            self.frames.append(frame)
            if predicate(frame):
                return frame
        raise AssertionError(f"expected frame not received; saw {self.frames}")

    def next_ack(self) -> dict:
        return self.next(lambda f: f.get("kind") == "ack")

    def next_scene_audio(self) -> dict:
        return self.next(lambda f: "scene_id" in f and "kind" not in f)

    def statuses(self) -> list[dict]:
        return [f["status"] for f in self.frames if f.get("kind") == "status"]


def test_valid_envelope_acked_and_narrated():
    envelope = make_envelope()
    with (
        TestClient(build_engine_app()) as client,
        client.websocket_connect("/v1/session") as ws,
    ):
        reader = Reader(ws)
        ws.send_text(json.dumps(envelope))

        ack = reader.next_ack()
        assert ack["moment_id"] == envelope["moment_id"]
        assert ack["ack"]["result"] == "accepted"

        scene = reader.next_scene_audio()
        jsonschema.validate(scene, SCENE_AUDIO_SCHEMA)
        assert scene["moment_id"] == envelope["moment_id"]
        assert scene["format"] == "wav_complete"
        assert scene["narration"]

        created = datetime.fromisoformat(scene["created_at"])
        play_by = datetime.fromisoformat(scene["play_by"])
        assert play_by - created == timedelta(seconds=60)

        with wave.open(io.BytesIO(base64.b64decode(scene["audio_b64"]))) as wav:
            assert wav.getframerate() == scene["sample_rate"]
            assert wav.getnframes() > 0

        # Busy status surfaced while the moment was in flight, idle after.
        reader.next(lambda f: f.get("kind") == "status" and f["status"]["busy"] is False)
        assert any(s["busy"] for s in reader.statuses())


def test_invalid_envelope_rejected_with_detail():
    envelope = make_envelope()
    del envelope["frames"]
    with (
        TestClient(build_engine_app()) as client,
        client.websocket_connect("/v1/session") as ws,
    ):
        ws.send_text(json.dumps(envelope))
        ack = Reader(ws).next_ack()
        assert ack["ack"]["result"] == "rejected"
        assert ack["moment_id"] == envelope["moment_id"]
        assert 0 < len(ack["ack"]["detail"]) <= 200


def test_non_json_frame_rejected():
    with (
        TestClient(build_engine_app()) as client,
        client.websocket_connect("/v1/session") as ws,
    ):
        ws.send_text("{not json")
        ack = Reader(ws).next_ack()
        assert ack["ack"]["result"] == "rejected"
        assert ack["moment_id"] is None


def test_duplicate_moment_id_acked_duplicate():
    envelope = make_envelope()
    with (
        TestClient(build_engine_app()) as client,
        client.websocket_connect("/v1/session") as ws,
    ):
        reader = Reader(ws)
        ws.send_text(json.dumps(envelope))
        assert reader.next_ack()["ack"]["result"] == "accepted"
        reader.next_scene_audio()

        ws.send_text(json.dumps(envelope))
        ack = reader.next_ack()
        assert ack["ack"]["result"] == "duplicate"
        assert ack["moment_id"] == envelope["moment_id"]


def test_coalescing_drops_queued_moment(monkeypatch):
    release = threading.Event()

    def slow_narrate(image, style_key=DEFAULT_STYLE_KEY, scene_hint="", backend=None):
        assert release.wait(timeout=10)
        return Narration(
            text="The queue was always going to thin itself out.",
            style_key=style_key,
            backend="mock",
            model_id="mock-narrator-0",
            latency_s=0.0,
        )

    monkeypatch.setattr("small_cuts.narrator.narrate", slow_narrate)
    e1, e2, e3 = make_envelope(), make_envelope(), make_envelope()
    with (
        TestClient(build_engine_app()) as client,
        client.websocket_connect("/v1/session") as ws,
    ):
        reader = Reader(ws)
        ws.send_text(json.dumps(e1))
        ack1 = reader.next_ack()  # e1 goes straight to processing
        ws.send_text(json.dumps(e2))
        ack2 = reader.next_ack()  # e2 waits in the single queue slot
        ws.send_text(json.dumps(e3))
        ack3 = reader.next_ack()  # e3 replaces e2 -> e2 dropped first
        ack4 = reader.next_ack()

        assert (ack1["moment_id"], ack1["ack"]["result"]) == (e1["moment_id"], "accepted")
        assert (ack2["moment_id"], ack2["ack"]["result"]) == (e2["moment_id"], "accepted")
        assert (ack3["moment_id"], ack3["ack"]["result"]) == (e2["moment_id"], "dropped_coalesced")
        assert (ack4["moment_id"], ack4["ack"]["result"]) == (e3["moment_id"], "accepted")

        release.set()
        scenes = [reader.next_scene_audio(), reader.next_scene_audio()]
        assert [s["moment_id"] for s in scenes] == [e1["moment_id"], e3["moment_id"]]

        reader.next(lambda f: f.get("kind") == "status" and f["status"]["busy"] is False)
        busy_depths = [s["queue_depth"] for s in reader.statuses() if s["busy"]]
        assert busy_depths and max(busy_depths) == 1  # queue depth never exceeded 1


def test_narration_failure_sends_error_frame(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("model fell over")

    monkeypatch.setattr("small_cuts.narrator.narrate", boom)
    envelope = make_envelope()
    with (
        TestClient(build_engine_app()) as client,
        client.websocket_connect("/v1/session") as ws,
    ):
        reader = Reader(ws)
        ws.send_text(json.dumps(envelope))
        assert reader.next_ack()["ack"]["result"] == "accepted"

        error = reader.next(lambda f: f.get("kind") == "error")
        assert error["moment_id"] == envelope["moment_id"]
        assert error["error"]["stage"] == "narration"
        assert error["error"]["retryable"] is True
        assert "model fell over" in error["error"]["message"]

        # The socket survives: a fresh envelope is still admitted.
        ws.send_text(json.dumps(make_envelope()))
        assert reader.next_ack()["ack"]["result"] == "accepted"


def test_tts_failure_sends_error_frame(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("kokoro oom")

    monkeypatch.setattr("small_cuts.tts.speak", boom)
    with (
        TestClient(build_engine_app()) as client,
        client.websocket_connect("/v1/session") as ws,
    ):
        reader = Reader(ws)
        ws.send_text(json.dumps(make_envelope()))
        error = reader.next(lambda f: f.get("kind") == "error")
        assert error["error"]["stage"] == "tts"
        assert error["error"]["retryable"] is True


def test_oversized_decoded_frame_sends_validation_error():
    # The declared width/height satisfy the schema; the pixels are what must be trusted.
    big = io.BytesIO()
    Image.new("RGB", (1100, 16), (10, 20, 30)).save(big, "JPEG")
    envelope = make_envelope()
    envelope["frames"][0]["jpeg_b64"] = base64.b64encode(big.getvalue()).decode()
    with (
        TestClient(build_engine_app()) as client,
        client.websocket_connect("/v1/session") as ws,
    ):
        reader = Reader(ws)
        ws.send_text(json.dumps(envelope))
        assert reader.next_ack()["ack"]["result"] == "accepted"

        error = reader.next(lambda f: f.get("kind") == "error")
        assert error["moment_id"] == envelope["moment_id"]
        assert error["error"]["stage"] == "validation"
        assert error["error"]["code"] == "frame_exceeds_cap"
        assert error["error"]["retryable"] is False


def test_corrupt_jpeg_sends_validation_error_not_retryable():
    envelope = make_envelope()
    envelope["frames"][0]["jpeg_b64"] = base64.b64encode(b"definitely not a jpeg").decode()
    with (
        TestClient(build_engine_app()) as client,
        client.websocket_connect("/v1/session") as ws,
    ):
        reader = Reader(ws)
        ws.send_text(json.dumps(envelope))
        assert reader.next_ack()["ack"]["result"] == "accepted"

        error = reader.next(lambda f: f.get("kind") == "error")
        assert error["error"]["stage"] == "validation"
        assert error["error"]["code"] == "frame_decode_failed"
        assert error["error"]["retryable"] is False

        # The socket survives: a healthy envelope still narrates.
        ws.send_text(json.dumps(make_envelope()))
        assert reader.next_ack()["ack"]["result"] == "accepted"
        reader.next_scene_audio()


def test_failed_moment_resend_is_reprocessed(monkeypatch):
    calls = {"n": 0}

    def flaky_narrate(image, style_key=DEFAULT_STYLE_KEY, scene_hint="", backend=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient model failure")
        return Narration(
            text="Second time lucky.",
            style_key=style_key,
            backend="mock",
            model_id="mock-narrator-0",
            latency_s=0.0,
        )

    monkeypatch.setattr("small_cuts.narrator.narrate", flaky_narrate)
    envelope = make_envelope()
    with (
        TestClient(build_engine_app()) as client,
        client.websocket_connect("/v1/session") as ws,
    ):
        reader = Reader(ws)
        ws.send_text(json.dumps(envelope))
        assert reader.next_ack()["ack"]["result"] == "accepted"
        error = reader.next(lambda f: f.get("kind") == "error")
        assert error["error"]["retryable"] is True

        # retryable:true is honest — the same moment_id is admitted again, not "duplicate".
        ws.send_text(json.dumps(envelope))
        assert reader.next_ack()["ack"]["result"] == "accepted"
        scene = reader.next_scene_audio()
        assert scene["moment_id"] == envelope["moment_id"]
        assert calls["n"] == 2

        # Success restores permanent dedupe.
        ws.send_text(json.dumps(envelope))
        assert reader.next_ack()["ack"]["result"] == "duplicate"


def test_binary_frame_rejected_and_socket_survives():
    with (
        TestClient(build_engine_app()) as client,
        client.websocket_connect("/v1/session") as ws,
    ):
        reader = Reader(ws)
        ws.send_bytes(b"\x89PNG\r\n\x1a\n")
        ack = reader.next_ack()
        assert ack["ack"]["result"] == "rejected"
        assert ack["moment_id"] is None
        assert "binary" in ack["ack"]["detail"]

        ws.send_text(json.dumps(make_envelope()))
        assert reader.next_ack()["ack"]["result"] == "accepted"
        reader.next_scene_audio()


def test_scene_audio_schema_drift_sends_storage_error(monkeypatch):
    class DriftedValidator:
        def validate(self, payload):
            raise jsonschema.ValidationError("payload drifted from scene-audio schema")

    monkeypatch.setattr("small_cuts.engine.session._SCENE_AUDIO", DriftedValidator())
    envelope = make_envelope()
    with (
        TestClient(build_engine_app()) as client,
        client.websocket_connect("/v1/session") as ws,
    ):
        reader = Reader(ws)
        ws.send_text(json.dumps(envelope))
        assert reader.next_ack()["ack"]["result"] == "accepted"

        error = reader.next(lambda f: f.get("kind") == "error")
        assert error["moment_id"] == envelope["moment_id"]
        assert error["error"]["stage"] == "storage"
        assert error["error"]["code"] == "scene_audio_schema_drift"
        assert error["error"]["retryable"] is False

        # The drain task survived schema drift: the next envelope is still admitted.
        ws.send_text(json.dumps(make_envelope()))
        assert reader.next_ack()["ack"]["result"] == "accepted"


def test_sink_receives_scene_dict():
    scenes: list[dict] = []
    envelope = make_envelope()
    with (
        TestClient(build_engine_app(scene_sink=scenes.append)) as client,
        client.websocket_connect("/v1/session") as ws,
    ):
        reader = Reader(ws)
        ws.send_text(json.dumps(envelope))
        audio_frame = reader.next_scene_audio()
        reader.next(lambda f: f.get("kind") == "status" and f["status"]["busy"] is False)

    assert len(scenes) == 1
    scene = scenes[0]
    assert scene["scene_id"] == audio_frame["scene_id"]
    assert scene["moment_id"] == envelope["moment_id"]
    assert scene["session_id"] == envelope["session_id"]
    assert scene["captured_at"] == envelope["captured_at"]
    assert scene["created_at"] == audio_frame["created_at"]
    assert scene["style_key"] == envelope["context"]["style_key"]
    assert scene["narration"] == audio_frame["narration"]
    assert isinstance(scene["image"], Image.Image)
    assert isinstance(scene["audio"], np.ndarray)
    assert scene["sample_rate"] == audio_frame["sample_rate"]
    latency = scene["latency_ms"]
    assert set(latency) == {"queue", "narration", "tts", "total"}
    assert all(isinstance(v, int) and v >= 0 for v in latency.values())


def test_sink_receives_clip_frames_sorted_by_timestamp_offset():
    def jpeg_b64(color):
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), color).save(buffer, "JPEG")
        return base64.b64encode(buffer.getvalue()).decode()

    scenes: list[dict] = []
    envelope = make_envelope()
    selected = envelope["frames"][0]
    selected["ts_offset_ms"] = 0
    selected["jpeg_b64"] = jpeg_b64((255, 0, 0))
    envelope["frames"] = [
        selected,
        {"jpeg_b64": jpeg_b64((0, 0, 255)), "width": 8, "height": 8, "ts_offset_ms": -2000},
        {"jpeg_b64": jpeg_b64((0, 255, 0)), "width": 8, "height": 8, "ts_offset_ms": -1000},
    ]
    with (
        TestClient(build_engine_app(scene_sink=scenes.append)) as client,
        client.websocket_connect("/v1/session") as ws,
    ):
        reader = Reader(ws)
        ws.send_text(json.dumps(envelope))
        reader.next_scene_audio()
        reader.next(lambda f: f.get("kind") == "status" and f["status"]["busy"] is False)

    assert len(scenes) == 1
    clip_frames = scenes[0]["clip_frames"]
    assert len(clip_frames) == 3
    assert [frame.getpixel((0, 0)) for frame in clip_frames] == [
        pytest.approx((0, 0, 255), abs=10),
        pytest.approx((0, 255, 0), abs=10),
        pytest.approx((255, 0, 0), abs=10),
    ]


def test_style_and_hint_wiring(monkeypatch):
    captured: list[dict] = []

    def spy_narrate(image, style_key=DEFAULT_STYLE_KEY, scene_hint="", backend=None):
        captured.append({"style_key": style_key, "scene_hint": scene_hint})
        return Narration(
            text="Noted.", style_key=style_key, backend="mock", model_id="m", latency_s=0.0
        )

    monkeypatch.setattr("small_cuts.narrator.narrate", spy_narrate)
    hinted = make_envelope()
    hinted["context"]["user_hint"] = "look at the boats"
    bare = make_envelope()
    del bare["context"]
    with (
        TestClient(build_engine_app()) as client,
        client.websocket_connect("/v1/session") as ws,
    ):
        reader = Reader(ws)
        ws.send_text(json.dumps(hinted))
        reader.next_scene_audio()
        ws.send_text(json.dumps(bare))
        reader.next_scene_audio()

    assert captured[0] == {"style_key": "symmetrist", "scene_hint": "look at the boats"}
    assert captured[1] == {"style_key": DEFAULT_STYLE_KEY, "scene_hint": ""}
