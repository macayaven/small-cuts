"""Contract enforcement: golden samples must validate against the schemas.

Each team's CI runs this. A producer changing its message shape without a
schema PR fails here, loudly, before anything ships.
"""

import base64
import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

CONTRACTS = Path(__file__).parent.parent / "docs" / "contracts"

_TINY_JPEG_B64 = base64.b64encode(b"\xff\xd8\xff\xdb fake-jpeg \xff\xd9").decode()

GOLDEN = {
    "moment.schema.json": {
        "contract_version": "1.1.0",
        "moment_id": "1b4e28ba-2fa1-11d2-883f-0016d3cca427",
        "session_id": "2026-06-12-morning-walk",
        "captured_at": "2026-06-12T09:30:00Z",
        "frames": [{"jpeg_b64": _TINY_JPEG_B64, "width": 768, "height": 1024, "ts_offset_ms": 0}],
        "gate": {"scene_change_score": 0.82, "motion_score": 0.4, "trigger": "scene_change"},
        "context": {
            "location_label": "Vilanova beach front",
            "style_key": "symmetrist",
            "battery_pct": 76,
            "network": "tailnet",
        },
        "prev_moment_id": None,
    },
    "narrated-scene.schema.json": {
        "contract_version": "1.3.0",
        "seq": 412,
        "captured_at": "2026-06-12T09:30:00Z",
        "scene_id": "9f1c7e4a-2fa1-11d2-883f-0016d3cca427",
        "moment_id": "1b4e28ba-2fa1-11d2-883f-0016d3cca427",
        "session_id": "2026-06-12-morning-walk",
        "created_at": "2026-06-12T09:30:08Z",
        "style_key": "symmetrist",
        "title": "The Bicycle Is Mustard Yellow",
        "narration": "The bicycle is mustard yellow, which is also the color of the railing.",
        "visibility": "private",
        "duration": 3.4,
        "keyframe_time": 0.0,
        "media": {
            "frame_url": "/media/9f1c7e4a/frame.jpg",
            "card_url": "/media/9f1c7e4a/card.webp",
            "audio_url": "/media/9f1c7e4a/voice.wav",
        },
        "engine": {
            "narrator_model": "Qwen/Qwen3-VL-8B-Instruct-GGUF",
            "narrator_backend": "llama_cpp",
            "tts_model": "hexgrad/Kokoro-82M",
            "latency_ms": {"queue": 40, "narration": 2400, "tts": 3500, "total": 6100},
        },
        "timed_captions": [
            {"t_start": 0.0, "t_end": 1.6, "text": "The bicycle is mustard yellow,"},
            {"t_start": 1.6, "t_end": 3.4, "text": "which is also the color of the railing."},
        ],
        "persona": "nature_doc",
        "language": "English",
    },
    "scene-audio.schema.json": {
        "contract_version": "1.1.0",
        "scene_id": "9f1c7e4a-2fa1-11d2-883f-0016d3cca427",
        "moment_id": "1b4e28ba-2fa1-11d2-883f-0016d3cca427",
        "created_at": "2026-06-12T09:30:08Z",
        "play_by": "2026-06-12T09:31:08Z",
        "format": "wav_complete",
        "audio_b64": _TINY_JPEG_B64,
        "sample_rate": 24000,
        "narration": "The bicycle is mustard yellow.",
    },
    "control.schema.json": {
        "contract_version": "1.1.0",
        "kind": "ack",
        "moment_id": "1b4e28ba-2fa1-11d2-883f-0016d3cca427",
        "ack": {"result": "accepted"},
    },
}


@pytest.mark.parametrize("schema_name", sorted(GOLDEN))
def test_golden_sample_validates(schema_name):
    schema = json.loads((CONTRACTS / schema_name).read_text())
    jsonschema.validate(GOLDEN[schema_name], schema)


def test_narrated_scene_v1_2_field_requires_1_2_0_version():
    # version-truth: the golden carries v1.2.0-only fields (duration/keyframe_time/timed_captions),
    # so stamping it "1.1.0" must fail — the schema binds contract_version to its field set.
    schema = json.loads((CONTRACTS / "narrated-scene.schema.json").read_text())
    downgraded = {**GOLDEN["narrated-scene.schema.json"], "contract_version": "1.1.0"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(downgraded, schema)


def test_narrated_scene_v1_3_field_requires_1_3_0_version():
    schema = json.loads((CONTRACTS / "narrated-scene.schema.json").read_text())
    sample = {
        **GOLDEN["narrated-scene.schema.json"],
        "persona": "nature_doc",
        "language": "English",
    }
    jsonschema.validate({**sample, "contract_version": "1.3.0"}, schema)  # ok
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**sample, "contract_version": "1.2.0"}, schema)  # persona forces 1.3.0


def test_narrated_scene_1_1_0_subset_still_validates():
    # a legacy producer emitting ONLY the 1.1.0 subset (no new fields) stays valid under 1.1.0.
    schema = json.loads((CONTRACTS / "narrated-scene.schema.json").read_text())
    legacy = {
        k: v
        for k, v in GOLDEN["narrated-scene.schema.json"].items()
        if k not in {"duration", "keyframe_time", "timed_captions", "persona", "language"}
    }
    legacy["contract_version"] = "1.1.0"
    jsonschema.validate(legacy, schema)


@pytest.mark.parametrize("schema_name", sorted(GOLDEN))
def test_unknown_fields_rejected(schema_name):
    schema = json.loads((CONTRACTS / schema_name).read_text())
    polluted = {**GOLDEN[schema_name], "freeform_extra": True}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(polluted, schema)


def test_moment_frame_size_capped():
    schema = json.loads((CONTRACTS / "moment.schema.json").read_text())
    oversized = json.loads(json.dumps(GOLDEN["moment.schema.json"]))
    oversized["frames"][0]["width"] = 2048  # violates the verified 1024px constraint
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(oversized, schema)


def test_moment_frame_count_allows_smoother_demo_clip_window():
    schema = json.loads((CONTRACTS / "moment.schema.json").read_text())
    sample = json.loads(json.dumps(GOLDEN["moment.schema.json"]))
    sample["frames"] = [{**sample["frames"][0], "ts_offset_ms": index * 166} for index in range(24)]

    jsonschema.validate(sample, schema)


def test_moment_frame_count_still_has_a_hard_cap():
    schema = json.loads((CONTRACTS / "moment.schema.json").read_text())
    oversized = json.loads(json.dumps(GOLDEN["moment.schema.json"]))
    oversized["frames"] = [
        {**oversized["frames"][0], "ts_offset_ms": index * 166} for index in range(25)
    ]

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(oversized, schema)


CONTROL_VARIANTS = [
    {
        "contract_version": "1.1.0",
        "kind": "error",
        "moment_id": "1b4e28ba-2fa1-11d2-883f-0016d3cca427",
        "error": {
            "stage": "tts",
            "code": "synth_failed",
            "message": "kokoro oom",
            "retryable": True,
        },
    },
    {
        "contract_version": "1.1.0",
        "kind": "status",
        "moment_id": None,
        "status": {"busy": True, "queue_depth": 1},
    },
]


@pytest.mark.parametrize("sample", CONTROL_VARIANTS)
def test_control_frame_variants(sample):
    schema = json.loads((CONTRACTS / "control.schema.json").read_text())
    jsonschema.validate(sample, schema)
