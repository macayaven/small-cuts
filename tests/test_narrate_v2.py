"""Phase 2 greenfield narration writer (src/small_cuts/narrate_v2.py).

The logic that the Modal /v2/narrate app depends on lives here in the importable product
package (modal isn't installed in the test venv), so it is unit-tested directly:
- build_narrated_scene produces a scene that is contract-valid by construction (fixes the
  §7 #3/#4 bugs: real uuid scene_id, no schema-violating top-level keys, engine{} block);
- publish_scene writes media BEFORE scene.json (atomic ordering, §7 #6) so a reader never
  sees a manifest/scene entry whose media is missing;
- the narration backend is a swappable interface with a GPU-free mock for CI/e2e.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from small_cuts import narrate_v2

jsonschema = pytest.importorskip("jsonschema")

SCHEMA = json.loads(
    (Path(__file__).parent.parent / "docs" / "contracts" / "narrated-scene.schema.json").read_text()
)


def _scene(**overrides):
    base = dict(
        narration="Una persona abre la puerta de un coche blanco estacionado en la acera.",
        title="Coche blanco",
        style_key="deadpan",
        media={"frame_url": "uploads/x/media/frame.jpg", "clip_url": "uploads/x/media/clip.mp4"},
        captured_at="2026-06-19T00:00:00Z",
        created_at="2026-06-19T00:00:05Z",
    )
    base.update(overrides)
    return narrate_v2.build_narrated_scene(**base)


def test_build_scene_is_contract_valid():
    jsonschema.validate(_scene(), SCHEMA)  # raises on any violation


def test_build_scene_uses_real_uuid_scene_id_not_modal_prefix():
    scene = _scene()
    # §7 #4: scene_id="modal-..." fails format:uuid; greenfield must emit a real uuid.
    assert not scene["scene_id"].startswith("modal-")
    import uuid

    uuid.UUID(scene["scene_id"])  # raises if not a real uuid
    uuid.UUID(scene["moment_id"])


def test_build_scene_has_no_schema_violating_top_level_keys():
    scene = _scene()
    # §7 #3: the old writer leaked model/tts_model/uploader/source/duration at top level,
    # which additionalProperties:false rejects. Provenance must live under engine{}.
    allowed = set(SCHEMA["properties"])
    assert set(scene) <= allowed, set(scene) - allowed


def test_build_scene_puts_provenance_under_engine():
    scene = _scene(
        engine={
            "narrator_model": "Qwen/Qwen3-Omni-30B-A3B-Instruct",
            "narrator_backend": "transformers",
            "tts_model": "Qwen/Qwen3-Omni-30B-A3B-Instruct",
        }
    )
    jsonschema.validate(scene, SCHEMA)
    assert scene["engine"]["narrator_backend"] == "transformers"


def test_build_scene_distinct_ids_per_call():
    assert _scene()["scene_id"] != _scene()["scene_id"]


def test_publish_writes_media_before_scene_json(tmp_path):
    # §7 #6: media must be uploaded before scene.json so a reader never sees a scene whose
    # media 404s. Record the order via a fake uploader.
    uploaded: list[str] = []

    def uploader(local: Path, remote: str) -> None:
        assert Path(local).exists()
        uploaded.append(remote)

    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"frame")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip")
    scene = _scene(scene_id="11111111-1111-1111-1111-111111111111")

    narrate_v2.publish_scene(
        uploader,
        prefix="relay",
        scene=scene,
        media_files={"frame.jpg": frame, "clip.mp4": clip},
        work_dir=tmp_path,
    )

    scene_idx = next(i for i, r in enumerate(uploaded) if r.endswith("scene.json"))
    media_idxs = [i for i, r in enumerate(uploaded) if "/media/" in r]
    assert media_idxs, "no media uploaded"
    assert max(media_idxs) < scene_idx, f"scene.json must be last: {uploaded}"


def test_publish_targets_uploads_prefix_for_scene_id(tmp_path):
    uploaded: list[str] = []
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"f")
    scene = _scene(scene_id="22222222-2222-2222-2222-222222222222")

    narrate_v2.publish_scene(
        lambda local, remote: uploaded.append(remote),
        prefix="relay",
        scene=scene,
        media_files={"frame.jpg": frame},
        work_dir=tmp_path,
    )

    assert all(
        r.startswith("relay/uploads/22222222-2222-2222-2222-222222222222/") for r in uploaded
    )
    assert any(r.endswith("/media/frame.jpg") for r in uploaded)
    assert any(r.endswith("/scene.json") for r in uploaded)


def test_mock_backend_returns_text_and_audio():
    backend = narrate_v2.MockNarrationBackend()
    result = backend.narrate(Path("/tmp/whatever.mp4"), style_key="deadpan", language="Spanish")
    assert result.text
    assert len(result.audio) > 0
    assert result.sample_rate > 0
    assert result.narrator_backend == "mock"


# ── captions: carrier-cut boundary + speech-relative cues (the aligner output → timed_captions) ──

_CARRIER = (
    "Preparando la voz del narrador en español de España. "
    "La descripción de la escena comienza ahora."
)


def _aligned(*pairs):
    return [{"word": w, "t_start": s, "t_end": e} for (w, s, e) in pairs]


def test_carrier_cut_index_finds_boundary():
    # carrier words, then the real narration; the boundary is the last carrier word's end-time.
    carrier_words = [(w, i * 0.4, i * 0.4 + 0.4) for i, w in enumerate(_CARRIER.split())]
    real_words = [("Una", 6.7, 7.0), ("persona", 7.0, 7.6)]
    words = _aligned(*carrier_words, *real_words)
    t_cut, idx = narrate_v2.carrier_cut_index(words, _CARRIER)
    assert idx == len(carrier_words) - 1
    assert abs(t_cut - carrier_words[-1][2]) < 1e-6
    assert words[idx + 1]["word"] == "Una"  # real narration starts right after


def test_cues_from_words_rebases_and_drops_carrier():
    carrier_words = [(w, i * 0.4, i * 0.4 + 0.4) for i, w in enumerate(_CARRIER.split())]
    t_cut = carrier_words[-1][2]
    real_words = [
        ("Una", t_cut + 0.05, t_cut + 0.4),
        ("persona", t_cut + 0.4, t_cut + 0.9),
        ("abre", t_cut + 0.9, t_cut + 1.2),
        ("la", t_cut + 1.2, t_cut + 1.3),
        ("puerta", t_cut + 1.3, t_cut + 1.8),
        ("del", t_cut + 1.8, t_cut + 1.95),
        ("coche", t_cut + 1.95, t_cut + 2.4),
    ]
    words = _aligned(*carrier_words, *real_words)
    cues = narrate_v2.cues_from_words(
        words, start_index=len(carrier_words), t_offset=t_cut, max_words=5
    )

    assert cues, "expected cues"
    assert all(c["t_start"] >= 0 and c["t_end"] >= c["t_start"] for c in cues)
    assert cues[0]["t_start"] < 0.1  # first real word rebased to ~0.05s
    joined = " ".join(c["text"] for c in cues)
    assert "Preparando" not in joined and "narrador" not in joined  # carrier dropped
    assert "persona" in joined
    assert all(len(c["text"].split()) <= 5 for c in cues)  # grouped


def test_build_scene_includes_timed_captions_when_provided():
    cues = [{"t_start": 0.0, "t_end": 1.2, "text": "Una persona abre la puerta"}]
    scene = _scene(timed_captions=cues)
    jsonschema.validate(scene, SCHEMA)  # v1.2.0 schema
    assert scene["timed_captions"] == cues


def test_build_scene_omits_timed_captions_when_absent():
    assert "timed_captions" not in _scene()  # additive/optional — absent by default


# ── v1.2.0: duration + keyframe_time + version-truth ──


def test_build_scene_stamps_contract_version_1_2_0():
    # The v2 writer emits v1.2.0-only fields, so it must stamp 1.2.0 — not the legacy 1.1.0.
    assert _scene()["contract_version"] == "1.2.0"


def test_build_scene_emits_duration_and_keyframe_time_when_provided():
    # duration = authoritative playback (narration-audio) length in s; keyframe_time = poster-frame
    # offset in the clip. Both additive/optional in v1.2.0.
    scene = _scene(duration=6.84, keyframe_time=3.2)
    jsonschema.validate(scene, SCHEMA)
    assert scene["duration"] == 6.84
    assert scene["keyframe_time"] == 3.2


def test_build_scene_omits_duration_and_keyframe_time_when_absent():
    scene = _scene()
    assert "duration" not in scene
    assert "keyframe_time" not in scene


def test_scene_carrying_a_v1_2_field_must_stamp_1_2_0():
    # version-truth (panel #1 footgun): a 1.2.0-only field under a "1.1.0" stamp must be REJECTED,
    # so a producer can never silently emit new fields while claiming the old version.
    scene = _scene(timed_captions=[{"t_start": 0.0, "t_end": 1.0, "text": "x"}])
    scene["contract_version"] = "1.1.0"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(scene, SCHEMA)


def test_production_shaped_scene_is_contract_valid_and_clean():
    # fold-in #1 for the REAL producer shape: mirror exactly what midcuts_narrate.py publishes
    # (engine{} provenance + duration + keyframe_time + all three media keys). A full validate
    # catches nested pollution in media{}/engine{} (both additionalProperties:false); the subset
    # checks guard top-level + nested keys against the schema.
    scene = _scene(
        media={
            "frame_url": "uploads/x/media/frame.jpg",
            "clip_url": "uploads/x/media/clip.mp4",
            "audio_url": "uploads/x/media/voice.wav",
        },
        duration=6.84,
        keyframe_time=0.0,
        engine={
            "narrator_model": "Qwen/Qwen3-Omni-30B-A3B-Instruct",
            "narrator_backend": "transformers",
            "tts_model": "Qwen/Qwen3-Omni-30B-A3B-Instruct",
        },
    )
    jsonschema.validate(scene, SCHEMA)
    assert set(scene) <= set(SCHEMA["properties"])
    assert set(scene["media"]) <= set(SCHEMA["properties"]["media"]["properties"])
    assert set(scene["engine"]) <= set(SCHEMA["properties"]["engine"]["properties"])


# ── push-not-poll: best-effort one-shot completion webhook to the Space relay hook ──


class _OkResponse:
    def raise_for_status(self) -> None:
        return None


def test_notify_relay_hook_skips_when_unconfigured():
    # No url and/or no token => no POST at all (push simply not configured); returns False so the
    # caller can tell it was a no-op. The bucket is the source of truth; the poll endpoint remains.
    calls: list[Any] = []

    def fake_post(*args: Any, **kwargs: Any) -> _OkResponse:
        calls.append((args, kwargs))
        return _OkResponse()

    assert narrate_v2.notify_relay_hook("", "", scene_id="s", seq=1, post=fake_post) is False
    assert (
        narrate_v2.notify_relay_hook("https://x/hook", "", scene_id="s", seq=1, post=fake_post)
        is False
    )
    assert narrate_v2.notify_relay_hook("", "tok", scene_id="s", seq=1, post=fake_post) is False
    assert calls == []


def test_notify_relay_hook_posts_pointer_with_bearer():
    calls: list[Any] = []

    def fake_post(url, *, headers, json, timeout) -> _OkResponse:
        calls.append((url, headers, json, timeout))
        return _OkResponse()

    ok = narrate_v2.notify_relay_hook(
        "https://space.example/small-cuts/hooks/relay-scene",
        "secret",
        scene_id="9f1c7e4a",
        seq=412,
        post=fake_post,
    )

    assert ok is True
    assert calls == [
        (
            "https://space.example/small-cuts/hooks/relay-scene",
            {"Authorization": "Bearer secret"},
            {"scene_id": "9f1c7e4a", "seq": 412},
            5.0,
        )
    ]


def test_notify_relay_hook_failure_is_non_fatal(capsys):
    # The scene is already durably published before the hook fires; a hook outage (Space paused/503,
    # network) must NEVER raise — it is logged and swallowed, returning False.
    def fake_post(*args: Any, **kwargs: Any):
        raise RuntimeError("space is paused (503)")

    ok = narrate_v2.notify_relay_hook(
        "https://x/hook", "secret", scene_id="s", seq=1, post=fake_post
    )

    assert ok is False
    assert "relay hook notify failed" in capsys.readouterr().err
