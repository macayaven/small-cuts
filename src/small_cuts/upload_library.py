from __future__ import annotations

import base64
import copy
import json
import os
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from PIL import Image

from .hf_relay import GRADIO_FILE_ROUTE, gradio_file_url

UPLOAD_LIBRARY_DIR_ENV = "SMALL_CUTS_UPLOAD_LIBRARY_DIR"
DEFAULT_UPLOAD_LIBRARY_DIR = "~/.small-cuts/uploads"
SOURCE = "upload"

_DATA_URI_RE = re.compile(r"^data:(?P<mime>[-\w./+]+);base64,(?P<body>.*)$", re.DOTALL)
_SCHEMA = """\
CREATE TABLE IF NOT EXISTS upload_scenes (
    scene_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    stored_at TEXT NOT NULL,
    payload TEXT NOT NULL
)"""


class LocalUploadLibrary:
    """Persistent upload shelf backed by SQLite plus stable media files."""

    def __init__(self, root: str | Path | None = None) -> None:
        base = root or os.environ.get(UPLOAD_LIBRARY_DIR_ENV) or DEFAULT_UPLOAD_LIBRARY_DIR
        self.root = Path(base).expanduser().resolve()
        self.media_dir = self.root / "media"
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.root / "uploads.sqlite3", check_same_thread=False)
        self._db.execute(_SCHEMA)
        self._db.commit()

    @classmethod
    def from_env(cls) -> LocalUploadLibrary:
        return cls()

    def save_scene(
        self,
        scene: dict[str, Any],
        *,
        source_video_path: str | Path | None = None,
    ) -> dict[str, Any]:
        payload = _json_safe_scene(scene)
        scene_id = _safe_path_segment(str(payload.get("scene_id") or "upload-scene"))
        scene_dir = self.media_dir / scene_id
        scene_dir.mkdir(parents=True, exist_ok=True)

        media = payload.get("media") if isinstance(payload.get("media"), dict) else {}
        payload["media"] = dict(media)

        frame_src = payload.pop("frame_src", None)
        if isinstance(frame_src, str):
            payload["media"]["frame_url"] = self._materialize_value(
                frame_src, scene_dir, "frame.jpg"
            )

        audio_src = payload.pop("audio_src", None)
        if isinstance(audio_src, str):
            payload["media"]["audio_url"] = self._materialize_value(
                audio_src, scene_dir, "voice.wav"
            )

        clip_src = payload.pop("clip_src", None)
        if source_video_path:
            clip_name = f"clip{Path(source_video_path).suffix or '.mp4'}"
            payload["media"]["clip_url"] = self._copy_file(
                Path(source_video_path), scene_dir, clip_name
            )
        elif isinstance(clip_src, str):
            payload["media"]["clip_url"] = self._materialize_value(clip_src, scene_dir, "clip.mp4")

        card_thumb = scene.get("card_thumb")
        if isinstance(card_thumb, Image.Image):
            card_path = scene_dir / "card.webp"
            card_thumb.save(card_path, "WEBP")
            payload["media"]["card_url"] = gradio_file_url(card_path)

        payload.pop("card_thumb", None)
        payload.setdefault("scene_id", scene_id)
        payload.setdefault("created_at", _now_iso())
        payload.setdefault("visibility", "private")
        payload["source"] = SOURCE
        payload["source_icon"] = SOURCE

        stored_at = _now_iso()
        with self._db:
            self._db.execute(
                """
                INSERT INTO upload_scenes (scene_id, created_at, stored_at, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(scene_id) DO UPDATE SET
                    created_at = excluded.created_at,
                    stored_at = excluded.stored_at,
                    payload = excluded.payload
                """,
                (
                    str(payload["scene_id"]),
                    str(payload["created_at"]),
                    stored_at,
                    json.dumps(payload, sort_keys=True),
                ),
            )
        return copy.deepcopy(payload)

    def list_scenes(self, limit: int = 60) -> list[dict[str, Any]]:
        rows = self._db.execute(
            """
            SELECT payload FROM (
                SELECT created_at, scene_id, payload
                FROM upload_scenes
                ORDER BY created_at DESC, scene_id DESC
                LIMIT ?
            )
            ORDER BY created_at ASC, scene_id ASC
            """,
            (int(limit),),
        ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def static_paths(self) -> list[Path]:
        return [self.root]

    def close(self) -> None:
        self._db.close()

    def _materialize_value(self, value: str, scene_dir: Path, filename: str) -> str:
        if value.startswith(("http://", "https://")):
            return value
        data = _decode_data_uri(value)
        if data is not None:
            target = scene_dir / filename
            target.write_bytes(data)
            return gradio_file_url(target)
        source = _local_path_from_url(value)
        if source is not None and source.is_file():
            return self._copy_file(source, scene_dir, filename)
        return value

    def _copy_file(self, source: Path, scene_dir: Path, filename: str) -> str:
        target = scene_dir / _safe_path_segment(filename)
        shutil.copy2(source, target)
        return gradio_file_url(target)


def _json_safe_scene(scene: dict[str, Any]) -> dict[str, Any]:
    clone = {key: value for key, value in scene.items() if key != "card_thumb"}
    return json.loads(json.dumps(clone, default=str))


def _decode_data_uri(value: str) -> bytes | None:
    match = _DATA_URI_RE.match(value)
    if not match:
        return None
    return base64.b64decode(match.group("body"), validate=False)


def _local_path_from_url(value: str) -> Path | None:
    if value.startswith(GRADIO_FILE_ROUTE):
        return Path(unquote(value[len(GRADIO_FILE_ROUTE) :]))
    path = Path(value)
    return path if path.is_absolute() else None


def _safe_path_segment(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "-" for ch in value)
    return cleaned.strip(".-") or "item"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
