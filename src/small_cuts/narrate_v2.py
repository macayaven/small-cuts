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
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

CONTRACT_VERSION = "1.1.0"
TITLE_MAX = 80
NARRATION_MAX = 2000

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
    scene_id: str | None = None,
    moment_id: str | None = None,
) -> dict[str, Any]:
    """Build a NarratedScene that validates against narrated-scene.schema.json by construction.

    Only schema keys are emitted (``additionalProperties: false``); provenance goes under
    ``engine{}``. ``scene_id``/``moment_id`` default to real uuids.
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
    return scene


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
