"""Greenfield narration writer for the v2 ``/v2/narrate`` pipeline (Mid Cuts).

This is the importable, GPU-free core that the Modal app depends on: build a contract-valid
``NarratedScene`` and publish it to the private ``macayaven/mid-cuts`` bucket with atomic
ordering. Keeping it here (not in ``modal_app/``) makes it unit-testable — ``modal`` is not in
the CI venv. The model-bearing Omni backend lives in the Modal app; this module only defines the
swappable backend interface plus a GPU-free mock.

Fixes baked in (DESIGN §7): real ``uuid`` ``scene_id`` (#4); no schema-violating top-level keys,
provenance under ``engine{}`` (#3); media uploaded before ``scene.json`` (#6). The write token is
the caller's concern — it passes an ``uploader`` bound to ``HfApi(token=WRITE_TOKEN)`` (#1).
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

CONTRACT_VERSION = "1.2.0"
TITLE_MAX = 80
NARRATION_MAX = 2000
RELAY_HOOK_TIMEOUT_S = 5.0

# (local file, remote bucket-relative path) -> None. The Modal app binds this to a token-scoped
# bucket writer; tests bind it to a recorder.
Uploader = Callable[[Path, str], None]


def build_narrated_scene(
    *,
    narration: str,
    title: str,
    style_key: str,
    media: dict[str, str],
    captured_at: str,
    created_at: str,
    session_id: str = "upload",
    seq: int = 0,
    visibility: str = "public",
    engine: dict[str, Any] | None = None,
    timed_captions: list[dict[str, Any]] | None = None,
    duration: float | None = None,
    keyframe_time: float | None = None,
    scene_id: str | None = None,
    moment_id: str | None = None,
) -> dict[str, Any]:
    """Build a NarratedScene that validates against narrated-scene.schema.json by construction.

    Only schema keys are emitted (``additionalProperties: false``); provenance goes under
    ``engine{}``. ``scene_id``/``moment_id`` default to real uuids. ``duration`` is the playback
    (narration-audio) length in seconds; ``keyframe_time`` is the poster frame's offset in the clip.
    """
    scene: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "scene_id": scene_id or str(uuid4()),
        "moment_id": moment_id or str(uuid4()),
        "session_id": session_id,
        "seq": seq,
        "captured_at": captured_at,
        "created_at": created_at,
        "style_key": style_key,
        "title": title[:TITLE_MAX],
        "narration": narration[:NARRATION_MAX],
        "visibility": visibility,
        "media": media,
    }
    if engine is not None:
        scene["engine"] = engine
    if duration is not None:
        scene["duration"] = duration
    if keyframe_time is not None:
        scene["keyframe_time"] = keyframe_time
    if timed_captions is not None:
        scene["timed_captions"] = timed_captions
    return scene


def _norm(text: str) -> str:
    return re.sub(r"[^0-9a-záéíóúñü]", "", text.lower())


def carrier_cut_index(words: list[dict[str, Any]], carrier: str) -> tuple[float, int]:
    """Find where the spoken warm-up carrier ends in the aligned word list.

    Accumulates normalized characters of the aligned words until they cover the carrier's
    normalized length; returns (carrier_end_time, last_carrier_word_index). Robust to the
    aligner's word/punctuation segmentation and to minor paraphrase (do_sample varies duration).
    """
    target = _norm(carrier)
    accumulated = ""
    for index, word in enumerate(words):
        accumulated += _norm(word["word"])
        if len(accumulated) >= len(target):
            return float(word["t_end"]), index
    return (float(words[-1]["t_end"]), len(words) - 1) if words else (0.0, -1)


def cues_from_words(
    words: list[dict[str, Any]],
    *,
    start_index: int = 0,
    t_offset: float = 0.0,
    max_words: int = 5,
) -> list[dict[str, Any]]:
    """Group aligned words (from start_index on) into ~max_words caption cues, rebased so times are
    relative to the trimmed audio (subtract t_offset, clamp >= 0). Drops the carrier words."""
    real = words[start_index:]
    cues: list[dict[str, Any]] = []
    for start in range(0, len(real), max_words):
        group = real[start : start + max_words]
        if not group:
            continue
        cues.append(
            {
                "t_start": max(0.0, round(float(group[0]["t_start"]) - t_offset, 3)),
                "t_end": max(0.0, round(float(group[-1]["t_end"]) - t_offset, 3)),
                "text": " ".join(w["word"] for w in group).strip(),
            }
        )
    return cues


def publish_scene(
    uploader: Uploader,
    *,
    prefix: str,
    scene: dict[str, Any],
    media_files: dict[str, Path],
    work_dir: Path,
) -> dict[str, str]:
    """Publish a scene under ``<prefix>/uploads/<scene_id>/`` with media-before-scene ordering.

    Uploads every media file first, then ``scene.json`` last, so a relay reading
    ``uploads/*/scene.json`` never sees a scene whose media has not landed yet (§7 #6). The relay
    discovers uploads by globbing scene.json, so no manifest mutation is needed.
    """
    scene_id = scene["scene_id"]
    base = f"{prefix.strip('/')}/uploads/{scene_id}"
    for name, path in media_files.items():
        uploader(Path(path), f"{base}/media/{name}")
    scene_path = Path(work_dir) / "scene.json"
    scene_path.write_text(json.dumps(scene, indent=2) + "\n")
    uploader(scene_path, f"{base}/scene.json")
    return {"scene_id": scene_id, "remote_prefix": base}


def notify_relay_hook(
    hook_url: str | None,
    hook_token: str | None,
    *,
    scene_id: str,
    seq: int,
    post: Callable[..., Any] | None = None,
) -> bool:
    """Best-effort one-shot push to the Space relay hook after a scene is published (push-not-poll).

    POSTs the pointer ``{scene_id, seq}`` with the shared Bearer; the Space re-reads the bucket and
    emits the scene on its SSE stream so open browsers refresh once. Returns ``True`` only when the
    hook accepts the push (HTTP 2xx). NEVER raises: the scene is already durably in the bucket, so a
    hook outage (Space paused/503, network) must not fail the publish — it is logged and swallowed.
    A no-op returning ``False`` when unconfigured (missing url or token): the bucket stays the
    source of truth and the headless poll endpoint remains the fallback. ``post`` is injectable
    (defaults to ``httpx.post``), mirroring this module's ``Uploader`` seam for unit tests.
    """
    url = (hook_url or "").strip()
    token = (hook_token or "").strip()
    if not (url and token):
        return False
    try:
        if post is None:
            import httpx  # inside the try so even a missing-httpx env degrades to a no-op

            post = httpx.post
        response = post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"scene_id": scene_id, "seq": seq},
            timeout=RELAY_HOOK_TIMEOUT_S,
        )
        response.raise_for_status()
        return True
    except Exception as exc:  # best-effort: the scene is already published; never fail on the hook
        print(f"narrate_v2: relay hook notify failed: {exc!r}", file=sys.stderr, flush=True)
        return False


@dataclass(frozen=True)
class NarrationResult:
    """One narration pass: text + speech + provenance (matches the contract's engine enum)."""

    text: str
    audio: Any  # samples — numpy array from real backends; a plain list from the mock
    sample_rate: int
    narrator_model: str
    tts_model: str
    narrator_backend: str  # contract enum: "llama_cpp" | "transformers" | "mock"
    title: str = ""


class NarrationBackend(Protocol):
    """Swappable narration backend — the modular seam the design requires."""

    def narrate(self, clip_path: Path, *, style_key: str, language: str) -> NarrationResult: ...


class MockNarrationBackend:
    """GPU-free backend for CI and local end-to-end tests (no model load)."""

    def narrate(
        self, clip_path: Path, *, style_key: str = "deadpan", language: str = "English"
    ) -> NarrationResult:
        stem = Path(clip_path).stem
        return NarrationResult(
            text=f"[mock {language}] a flat description of {stem}.",
            audio=[0.0] * 2400,  # 0.1 s @ 24 kHz placeholder
            sample_rate=24_000,
            narrator_model="mock",
            tts_model="mock",
            narrator_backend="mock",
            title=stem.replace("-", " ").title()[:TITLE_MAX],
        )
