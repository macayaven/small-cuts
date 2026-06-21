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
from small_cuts.narrate_v2 import (
    MAX_CONTEXT_CHARS,
    PERSONA_DEFAULT_KEY,
    PERSONA_LABELS,
    PERSONA_STEERS,
    persona_choices,
    resolve_persona_steer,
)

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


def test_plan_carrier_cut_returns_trim_and_rebased_captions():
    carrier_words = [(w, i * 0.4, i * 0.4 + 0.4) for i, w in enumerate(_CARRIER.split())]
    t_cut_expected = carrier_words[-1][2]
    real_words = [
        ("Una", t_cut_expected + 0.05, t_cut_expected + 0.4),
        ("persona", t_cut_expected + 0.4, t_cut_expected + 0.9),
        ("abre", t_cut_expected + 0.9, t_cut_expected + 1.2),
    ]
    words = _aligned(*carrier_words, *real_words)
    t_cut, real_text, cues = narrate_v2.plan_carrier_cut(words, _CARRIER)
    assert abs(t_cut - t_cut_expected) < 1e-6
    assert real_text == "Una persona abre"  # carrier dropped, real narration kept
    assert cues and cues[0]["t_start"] < 0.1  # rebased so the trimmed audio starts at ~0
    joined = " ".join(c["text"] for c in cues)
    assert "Preparando" not in joined and "persona" in joined


def test_plan_carrier_cut_punctuation_only_tail_yields_no_text_and_no_captions():
    # A lone aligner "." after the carrier is not real narration → signal untrimmed, NO captions
    # (rebased cues on the untrimmed take would be misaligned).
    carrier_words = [(w, i * 0.4, i * 0.4 + 0.4) for i, w in enumerate(_CARRIER.split())]
    words = _aligned(*carrier_words, (".", 99.0, 99.1))
    _t_cut, real_text, cues = narrate_v2.plan_carrier_cut(words, _CARRIER)
    assert real_text == ""
    assert cues == []


def test_build_scene_includes_timed_captions_when_provided():
    cues = [{"t_start": 0.0, "t_end": 1.2, "text": "Una persona abre la puerta"}]
    scene = _scene(timed_captions=cues)
    jsonschema.validate(scene, SCHEMA)  # v1.3.0 schema
    assert scene["timed_captions"] == cues


def test_build_scene_omits_timed_captions_when_absent():
    assert "timed_captions" not in _scene()  # additive/optional — absent by default


# ── v1.2.0: duration + keyframe_time + version-truth ──


def test_build_scene_stamps_contract_version_1_3_0():
    # The v2 writer now stamps 1.3.0 (bumped from 1.2.0 with persona/language additive fields).
    assert _scene()["contract_version"] == "1.3.0"


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


# ── v1.3.0: persona + language ──


def test_build_narrated_scene_emits_persona_and_language():
    from small_cuts import narrate_v2

    scene = narrate_v2.build_narrated_scene(
        narration="x",
        title="t",
        style_key="nature_doc",
        media={"clip_url": "c", "audio_url": "a", "frame_url": "f"},
        captured_at="2026-06-20T00:00:00Z",
        created_at="2026-06-20T00:00:00Z",
        persona="nature_doc",
        language="English",
    )
    assert scene["persona"] == "nature_doc"
    assert scene["language"] == "English"
    assert scene["contract_version"] == "1.3.0"


def test_build_narrated_scene_omits_persona_language_when_absent():
    from small_cuts import narrate_v2

    scene = narrate_v2.build_narrated_scene(
        narration="x",
        title="t",
        style_key="deadpan",
        media={"clip_url": "c", "audio_url": "a", "frame_url": "f"},
        captured_at="2026-06-20T00:00:00Z",
        created_at="2026-06-20T00:00:00Z",
    )
    assert "persona" not in scene and "language" not in scene
    assert scene["contract_version"] == "1.3.0"


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


# ── narration-quality: language config (native prompts + warm-up carrier) ──
#
# The selectable languages (en/es/fr — the by-ear-validated set) must each carry a native-language
# narration prompt, a warm-up carrier, a prime instruction, and a title prompt. Anything else must
# degrade gracefully to an English-base prompt with no carrier (so the aligner step is skipped).

_SELECTABLE = ("English", "Spanish", "French")


@pytest.mark.parametrize("language", _SELECTABLE)
def test_selectable_languages_are_fully_configured(language):
    assert language in narrate_v2.NATIVE_PROMPTS
    assert language in narrate_v2.PRIME_CARRIER
    assert language in narrate_v2.PRIME_INSTRUCTION
    assert language in narrate_v2.TITLE_PROMPTS
    # native prompt + title prompt are (system, user) pairs of non-empty strings
    for pair in (narrate_v2.NATIVE_PROMPTS[language], narrate_v2.TITLE_PROMPTS[language]):
        system, user = pair
        assert system.strip() and user.strip()


def test_every_carrier_has_a_prime_instruction_template():
    # prime needs BOTH a carrier and an instruction; a carrier with no template would crash .format
    assert set(narrate_v2.PRIME_CARRIER) <= set(narrate_v2.PRIME_INSTRUCTION)
    for template in narrate_v2.PRIME_INSTRUCTION.values():
        assert "{carrier}" in template  # the instruction interpolates the carrier text


def test_build_narration_prompts_uses_native_pair_for_native_language():
    system, user = narrate_v2.build_narration_prompts("Spanish", prime=False)
    assert (system, user) == narrate_v2.NATIVE_PROMPTS["Spanish"]
    assert "español" in system.lower()
    assert "write the narration in" not in system.lower()  # not the anglophone fallback


def test_build_narration_prompts_falls_back_to_english_base_for_unknown_language():
    system, user = narrate_v2.build_narration_prompts("German", prime=False)
    assert system.startswith(narrate_v2.DEADPAN_SYS)
    assert "Write the narration in German." in system
    assert user == narrate_v2.USER_PROMPT


def test_build_narration_prompts_prime_appends_carrier_and_instruction():
    base_system, _ = narrate_v2.build_narration_prompts("Spanish", prime=False)
    primed_system, _ = narrate_v2.build_narration_prompts("Spanish", prime=True)
    assert primed_system.startswith(base_system)  # native prompt preserved, instruction appended
    assert narrate_v2.PRIME_CARRIER["Spanish"] in primed_system  # carrier text embedded


def test_build_narration_prompts_prime_is_noop_without_a_carrier():
    # German has no carrier → prime must NOT alter the prompt (and must not raise on a missing tmpl)
    primed = narrate_v2.build_narration_prompts("German", prime=True)
    plain = narrate_v2.build_narration_prompts("German", prime=False)
    assert primed == plain


# ── narration-quality: free-text context steer (Phase 5 step 1 — steers HOW it is told) ──


@pytest.mark.parametrize("language", ["English", "Spanish", "French", "German"])
@pytest.mark.parametrize("prime", [False, True])
def test_build_narration_prompts_empty_context_is_byte_identical(language, prime):
    # The deadpan default was ratified by ear; a blank context must not perturb a single byte.
    base = narrate_v2.build_narration_prompts(language, prime=prime)
    assert narrate_v2.build_narration_prompts(language, prime=prime, context="") == base
    assert narrate_v2.build_narration_prompts(language, prime=prime, context="   ") == base


def test_build_narration_prompts_injects_context_as_manner_steer():
    base_system, base_user = narrate_v2.build_narration_prompts("Spanish", prime=False)
    system, user = narrate_v2.build_narration_prompts(
        "Spanish", prime=False, context="como una enfermera agotada del turno de noche"
    )
    assert system.startswith(base_system)  # native deadpan spec preserved, steer appended after
    assert "como una enfermera agotada del turno de noche" in system
    assert user == base_user  # the manner steer lives in the system prompt, not the task turn


def test_build_narration_prompts_context_precedes_carrier_instruction():
    # The carrier instruction must stay LAST so the Talker still opens with the carrier verbatim
    # (the aligner trim depends on it); the context steer is injected before the prime block.
    system, _ = narrate_v2.build_narration_prompts(
        "Spanish", prime=True, context="en tono nostálgico"
    )
    carrier_tail = narrate_v2.PRIME_INSTRUCTION["Spanish"].format(
        carrier=narrate_v2.PRIME_CARRIER["Spanish"]
    )
    assert system.endswith(carrier_tail)
    assert system.index("en tono nostálgico") < system.index(carrier_tail)


def test_build_narration_prompts_caps_context_length():
    system, _ = narrate_v2.build_narration_prompts("English", prime=False, context="x" * 500)
    assert "x" * narrate_v2.MAX_CONTEXT_CHARS in system
    assert "x" * (narrate_v2.MAX_CONTEXT_CHARS + 1) not in system


def test_build_narration_prompts_context_unknown_language_uses_english_template():
    system, _ = narrate_v2.build_narration_prompts(
        "German", prime=False, context="hushed and reverent"
    )
    assert "hushed and reverent" in system  # injected even for fallback languages


def test_clean_context_collapses_whitespace_and_caps():
    assert narrate_v2.clean_context("  hello   world  ") == "hello world"
    assert narrate_v2.clean_context("") == ""
    assert narrate_v2.clean_context("   ") == ""
    assert len(narrate_v2.clean_context("y" * 1000)) == narrate_v2.MAX_CONTEXT_CHARS


def test_has_carrier_true_for_selectable_false_for_other():
    assert narrate_v2.has_carrier("French") is True
    assert narrate_v2.has_carrier("German") is False


def test_build_title_prompts_uses_native_language():
    system, user = narrate_v2.build_title_prompts("French")
    assert system.strip() and user.strip()
    assert "français" in system.lower()


def test_build_title_prompts_falls_back_for_unknown_language():
    system, user = narrate_v2.build_title_prompts("German")
    assert "German" in system  # fallback asks for the title in the requested language
    assert user.strip()


# ── narration-quality: model-title cleaner (regression #2 — titles must be model titles) ──


def test_clean_model_title_passes_through_a_clean_title():
    assert narrate_v2.clean_model_title("The White Car", fallback="x") == "The White Car"


def test_clean_model_title_strips_surrounding_quotes():
    assert narrate_v2.clean_model_title('"The White Car"', fallback="x") == "The White Car"


def test_clean_model_title_strips_markdown_bold():
    assert narrate_v2.clean_model_title("**The White Car**", fallback="x") == "The White Car"


def test_clean_model_title_strips_leading_label():
    assert narrate_v2.clean_model_title("Title: The White Car", fallback="x") == "The White Car"
    es = narrate_v2.clean_model_title("Título: El coche blanco", fallback="x")
    assert es == "El coche blanco"


def test_clean_model_title_strips_trailing_punctuation():
    assert narrate_v2.clean_model_title("The White Car.", fallback="x") == "The White Car"


def test_clean_model_title_takes_first_real_title_line():
    # models sometimes add a trailing parenthetical gloss; the title is the first real line
    raw = "The White Car\n\n(a short, evocative two-word title)"
    assert narrate_v2.clean_model_title(raw, fallback="x") == "The White Car"


def test_clean_model_title_skips_a_label_only_first_line():
    # "Title:\nThe White Car" — the label line cleans to empty, so fall through to the next line
    assert narrate_v2.clean_model_title("Title:\nThe White Car", fallback="x") == "The White Car"


def test_clean_model_title_strips_guillemets():
    fr = narrate_v2.clean_model_title("«La voiture blanche»", fallback="x")
    assert fr == "La voiture blanche"


def test_clean_model_title_empty_or_blank_uses_fallback():
    assert narrate_v2.clean_model_title("", fallback="Fallback Title") == "Fallback Title"
    assert narrate_v2.clean_model_title("   \n  ", fallback="Fallback Title") == "Fallback Title"


def test_clean_model_title_caps_length_to_title_max():
    long_title = "word " * 40  # 200 chars
    cleaned = narrate_v2.clean_model_title(long_title, fallback="x")
    assert len(cleaned) <= narrate_v2.TITLE_MAX


def test_clean_model_title_fallback_is_also_capped():
    cleaned = narrate_v2.clean_model_title("", fallback="z" * 200)
    assert len(cleaned) == narrate_v2.TITLE_MAX


def test_clean_model_title_never_returns_empty_even_when_fallback_is_empty():
    # review #3/#6: schema has no minLength, but an empty slate title is bad UX; guarantee non-empty
    # when BOTH the model title and the derive_title fallback clean to empty (empty narration case).
    assert narrate_v2.clean_model_title("", fallback="") == "Untitled"
    assert narrate_v2.clean_model_title("   ", fallback="  ") == "Untitled"


# ── narration-quality: carrier-cut safety net (review #4/#5) ──


def test_has_speech_content_true_for_words_false_for_punctuation():
    # review #5: a lone aligner punctuation token (".") must NOT count as real narration, or the
    # carrier-cut gate would publish a near-empty trimmed take instead of falling back to untrimmed.
    assert narrate_v2.has_speech_content("Una persona abre la puerta") is True
    assert narrate_v2.has_speech_content(".") is False
    assert narrate_v2.has_speech_content("  ,  …  ") is False
    assert narrate_v2.has_speech_content("") is False


def test_carrier_cut_index_returns_last_word_when_carrier_never_fully_matched():
    # review #4: if the aligned words are shorter than the carrier, cut at the last word — the
    # caller then sees real_text == "" (words[idx+1:] empty) and falls back to the untrimmed take.
    words = _aligned(("Preparando", 0.0, 0.4), ("la", 0.4, 0.6))
    t_cut, idx = narrate_v2.carrier_cut_index(words, _CARRIER)  # carrier is far longer
    assert idx == len(words) - 1
    assert t_cut == words[-1]["t_end"]
    assert " ".join(w["word"] for w in words[idx + 1 :]).strip() == ""  # untrimmed fallback


def test_carrier_cut_index_empty_words_returns_sentinel():
    # review #4: no aligned words at all → (0.0, -1); words[idx+1:] over [] is empty → fallback.
    t_cut, idx = narrate_v2.carrier_cut_index([], _CARRIER)
    assert (t_cut, idx) == (0.0, -1)
    assert " ".join(w["word"] for w in [][idx + 1 :]).strip() == ""


# ── persona presets: in-code resolution (Task 1) ──

PERSONA_LANGS = ("English", "Spanish", "French")


def test_default_persona_resolves_to_empty_for_every_language():
    for lang in PERSONA_LANGS:
        assert resolve_persona_steer(PERSONA_DEFAULT_KEY, lang) == ""


def test_unknown_persona_resolves_to_empty():
    assert resolve_persona_steer("does-not-exist", "English") == ""


def test_known_persona_unknown_language_resolves_to_empty():
    # Only en/es/fr are exposed; any other language resolves to "" (spec: unknown -> empty).
    assert resolve_persona_steer("storybook", "German") == ""


def test_known_persona_resolves_to_native_string():
    for key in PERSONA_STEERS:
        for lang in PERSONA_LANGS:
            steer = resolve_persona_steer(key, lang)
            assert steer == PERSONA_STEERS[key][lang]
            assert steer.strip() != ""


def test_all_persona_steers_present_and_within_cap():
    # 6 non-default personas, each in all three languages, each within the wire cap.
    assert set(PERSONA_STEERS) == {
        "storybook",
        "magical_realism",
        "nature_doc",
        "fatalist",
        "nihilist",
        "reverie",
    }
    for key, by_lang in PERSONA_STEERS.items():
        assert set(by_lang) == set(PERSONA_LANGS), key
        for lang, steer in by_lang.items():
            assert 0 < len(steer) <= MAX_CONTEXT_CHARS, (key, lang, len(steer))


def test_persona_choices_lists_seven_with_default_first():
    choices = persona_choices()
    assert choices[0] == (PERSONA_LABELS[PERSONA_DEFAULT_KEY], PERSONA_DEFAULT_KEY)
    assert len(choices) == 7  # deadpan + 6 personas
    assert all(isinstance(label, str) and isinstance(key, str) for label, key in choices)
    assert {key for _, key in choices} == {PERSONA_DEFAULT_KEY, *PERSONA_STEERS}


# ── persona presets: Langfuse overlay (Task 2) ──


def test_persona_prompt_name_uses_lang_code():
    assert narrate_v2._persona_prompt_name("nature_doc", "Spanish") == (
        "midcuts-persona/nature_doc/es"
    )
    assert narrate_v2._persona_prompt_name("nature_doc", "Klingon") == (
        "midcuts-persona/nature_doc/en"
    )


def test_resolve_falls_back_to_incode_when_langfuse_absent(monkeypatch):
    # No client (unconfigured / import failure) → in-code string, never raises.
    monkeypatch.setattr(narrate_v2, "_langfuse_client", lambda: None)
    steer = resolve_persona_steer("nihilist", "English")
    assert steer == PERSONA_STEERS["nihilist"]["English"]


def test_resolve_uses_langfuse_value_when_available(monkeypatch):
    class _FakePrompt:
        def compile(self):
            return "OVERRIDDEN STEER FROM LANGFUSE"

    class _FakeClient:
        def __init__(self):
            self.calls = []

        def get_prompt(self, name, fallback):
            self.calls.append((name, fallback))
            return _FakePrompt()

    fake = _FakeClient()
    monkeypatch.setattr(narrate_v2, "_langfuse_client", lambda: fake)
    steer = resolve_persona_steer("nature_doc", "French")
    assert steer == "OVERRIDDEN STEER FROM LANGFUSE"
    # Called with the right name and the in-code fallback.
    assert fake.calls == [("midcuts-persona/nature_doc/fr", PERSONA_STEERS["nature_doc"]["French"])]


def test_resolve_falls_back_when_langfuse_raises(monkeypatch):
    class _BoomClient:
        def get_prompt(self, name, fallback):
            raise RuntimeError("network down")

    monkeypatch.setattr(narrate_v2, "_langfuse_client", lambda: _BoomClient())
    steer = resolve_persona_steer("storybook", "Spanish")
    assert steer == PERSONA_STEERS["storybook"]["Spanish"]


def test_default_persona_never_calls_langfuse(monkeypatch):
    def _boom():
        raise AssertionError("Langfuse must not be consulted for the default persona")

    monkeypatch.setattr(narrate_v2, "_langfuse_client", _boom)
    assert resolve_persona_steer(PERSONA_DEFAULT_KEY, "English") == ""
