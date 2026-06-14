"""Engine-side scene library: filesystem media + sqlite index (D6).

The real `SceneSink`. Every successful narration is persisted — frame JPEG,
title card, voice WAV, one sqlite row — and fanned out to live SSE
subscribers (D7). Blocking writes run in a worker thread via
`asyncio.to_thread`; the publish happens back on the event loop. Stored
entries and live events share the same NarratedScene shape, per
docs/contracts/narrated-scene.schema.json.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sqlite3
import sys
import threading
from pathlib import Path
from typing import Any

from PIL import Image

from small_cuts import narrator, tts
from small_cuts.title_card import derive_title, render_title_card

from .session import CONTRACT_VERSION, _wav_bytes

DEFAULT_ROOT = "~/.small-cuts/library"
OWNER = "carlos"  # v1 engines are single-user; the field is reserved for multi-user
VISIBILITIES = ("private", "shared", "public")
MEDIA_FILES = ("frame.jpg", "card.webp", "voice.wav", "clip.mp4")

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS scenes (
    scene_id    TEXT PRIMARY KEY,
    seq         INTEGER NOT NULL UNIQUE,
    moment_id   TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    style_key   TEXT NOT NULL,
    title       TEXT NOT NULL,
    narration   TEXT NOT NULL,
    visibility  TEXT NOT NULL DEFAULT 'private',
    owner       TEXT NOT NULL,
    engine      TEXT NOT NULL
)"""

_INSERT = """\
INSERT INTO scenes (scene_id, seq, moment_id, session_id, captured_at, created_at,
                    style_key, title, narration, visibility, owner, engine)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""


class SceneLibrary:
    """Scene store + in-process pub/sub. The instance itself is the async SceneSink.

    Layout: `<root>/library.sqlite3` + `<root>/media/<scene_id>/{frame.jpg,
    card.webp, voice.wav}`. One sqlite connection, guarded by a lock: the
    sink writes from worker threads, queries come from request handlers.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        base = root or os.environ.get("SMALL_CUTS_LIBRARY_DIR") or DEFAULT_ROOT
        self.root = Path(base).expanduser().resolve()
        self.media_dir = self.root / "media"
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()  # guards the connection and seq allocation
        self._db = sqlite3.connect(self.root / "library.sqlite3", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock, self._db:
            # WAL + busy_timeout: viewer reads don't block sink writes, and a
            # briefly locked database waits instead of raising immediately.
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA busy_timeout=5000")
            self._db.execute(_SCHEMA)
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []

    # -- the sink -----------------------------------------------------------------

    async def __call__(self, scene: dict[str, Any]) -> None:
        """SceneSink entry point: persist off the event loop, then publish.

        A failed store (disk full, sqlite error) must not be silent data loss:
        the mobile client already received its SceneAudio, so log to stderr and
        fan an error ControlFrame to the viewer stream — the timeline stays
        honest. `_hand_to_sink`'s suppression remains the last-resort backstop.
        """
        try:
            narrated = await asyncio.to_thread(self.store, scene)
        except Exception as exc:
            print(
                f"small_cuts.engine: library write failed for scene {scene['scene_id']}: {exc!r}",
                file=sys.stderr,
            )
            self.publish_event(
                {
                    "contract_version": CONTRACT_VERSION,
                    "kind": "error",
                    "moment_id": scene["moment_id"],
                    "error": {
                        "stage": "storage",
                        "code": "library_write_failed",
                        "message": str(exc)[:300],
                        "retryable": False,
                    },
                }
            )
            return
        self.publish_event(narrated)

    def publish_event(self, payload: dict[str, Any]) -> None:
        """Fan any event (stored scene or ControlFrame error) to live subscribers.

        Events without a seq (errors) are EPHEMERAL: not persisted, not in Last-Event-ID replay.
        """
        for queue in list(self._subscribers):
            queue.put_nowait(payload)

    def store(self, scene: dict[str, Any]) -> dict[str, Any]:
        """Persist media + index row (blocking); returns the stored NarratedScene."""
        scene_id: str = scene["scene_id"]
        narration: str = scene["narration"]
        style_key: str = scene["style_key"]
        title = derive_title(narration)

        scene_dir = self.media_dir / scene_id
        scene_dir.mkdir(parents=True, exist_ok=True)
        scene["image"].convert("RGB").save(scene_dir / "frame.jpg", "JPEG", quality=90)
        clip_frames = scene.get("clip_frames") or []
        if len(clip_frames) >= 2:
            try:
                _write_clip_mp4(scene_dir / "clip.mp4", clip_frames)
            except Exception as exc:
                print(
                    f"small_cuts.engine: clip write failed for scene {scene_id}: {exc!r}",
                    file=sys.stderr,
                )
        render_title_card(title, style_key).save(scene_dir / "card.webp", "WEBP")
        (scene_dir / "voice.wav").write_bytes(_wav_bytes(scene["audio"], scene["sample_rate"]))

        narrator_backend = narrator.get_backend()
        tts_backend = tts.get_tts_backend()
        engine = {
            "narrator_model": narrator_backend.model_id,
            "narrator_backend": narrator_backend.name,
            "tts_model": tts_backend.model_id,
            "latency_ms": scene["latency_ms"],
        }
        with self._lock, self._db:
            # max+1 under the lock: monotonic across the process AND across restarts.
            seq = self._db.execute("SELECT COALESCE(MAX(seq), -1) + 1 FROM scenes").fetchone()[0]
            self._db.execute(
                _INSERT,
                (
                    scene_id,
                    seq,
                    scene["moment_id"],
                    scene["session_id"],
                    scene["captured_at"],
                    scene["created_at"],
                    style_key,
                    title,
                    narration,
                    "private",
                    OWNER,
                    json.dumps(engine),
                ),
            )
        stored = self.get(scene_id)
        assert stored is not None  # the row was just inserted
        return stored

    # -- queries ---------------------------------------------------------------------

    def to_narrated_scene(self, row: sqlite3.Row) -> dict[str, Any]:
        """Contract-valid NarratedScene (1.1.0) for one stored row."""
        scene_id = row["scene_id"]
        media = {
            "frame_url": f"/media/{scene_id}/frame.jpg",
            "card_url": f"/media/{scene_id}/card.webp",
            "audio_url": f"/media/{scene_id}/voice.wav",
        }
        if (self.media_dir / scene_id / "clip.mp4").is_file():
            media["clip_url"] = f"/media/{scene_id}/clip.mp4"
        return {
            "contract_version": CONTRACT_VERSION,
            "scene_id": scene_id,
            "moment_id": row["moment_id"],
            "session_id": row["session_id"],
            "captured_at": row["captured_at"],
            "created_at": row["created_at"],
            "style_key": row["style_key"],
            "title": row["title"],
            "narration": row["narration"],
            "visibility": row["visibility"],
            "seq": row["seq"],
            "owner": row["owner"],
            "media": media,
            "engine": json.loads(row["engine"]),
        }

    def list_scenes(
        self,
        session_id: str | None = None,
        visibility: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Scenes ordered by `captured_at` — chronology, not arrival (D8 reorders)."""
        clauses, params = [], []
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if visibility is not None:
            clauses.append("visibility = ?")
            params.append(visibility)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM scenes{where} ORDER BY captured_at, seq LIMIT ?"
        with self._lock:
            rows = self._db.execute(query, (*params, limit)).fetchall()
        return [self.to_narrated_scene(row) for row in rows]

    def get(self, scene_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM scenes WHERE scene_id = ?", (scene_id,)
            ).fetchone()
        return self.to_narrated_scene(row) if row is not None else None

    def set_visibility(self, scene_id: str, visibility: str) -> dict[str, Any] | None:
        """The viewer's only write (D7). Returns the updated scene, or None if unknown."""
        if visibility not in VISIBILITIES:
            raise ValueError(f"Unknown visibility {visibility!r}; expected one of {VISIBILITIES}")
        with self._lock, self._db:
            updated = self._db.execute(
                "UPDATE scenes SET visibility = ? WHERE scene_id = ?", (visibility, scene_id)
            ).rowcount
        return self.get(scene_id) if updated else None

    def scenes_since(self, seq: int) -> list[dict[str, Any]]:
        """Scenes with seq > `seq`, ordered by seq — the SSE Last-Event-ID replay."""
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM scenes WHERE seq > ? ORDER BY seq", (seq,)
            ).fetchall()
        return [self.to_narrated_scene(row) for row in rows]

    def media_path(self, scene_id: str, filename: str) -> Path | None:
        """Resolve a media file, or None: unknown name, traversal, or missing file."""
        if filename not in MEDIA_FILES:
            return None
        path = (self.media_dir / scene_id / filename).resolve()
        if not path.is_relative_to(self.media_dir):  # traversal via scene_id
            return None
        return path if path.is_file() else None

    # -- pub/sub ----------------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """New-scene feed for one SSE connection; pair with `unsubscribe`."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        with contextlib.suppress(ValueError):
            self._subscribers.remove(queue)

    def close(self) -> None:
        with self._lock:
            self._db.close()


def _write_clip_mp4(path: Path, frames: list[Image.Image], fps: int = 3) -> None:
    """Render a small browser-playable MP4 from sampled POV frames."""
    import av

    rgb_frames = [frame.convert("RGB") for frame in frames]
    width, height = rgb_frames[0].size
    # H.264/yuv420p expects even dimensions. Preserve portrait aspect and only
    # shave one pixel if needed; capture frames are already downscaled upstream.
    width = max(2, width - (width % 2))
    height = max(2, height - (height % 2))

    container = av.open(str(path), "w")
    try:
        stream = container.add_stream("libx264", rate=fps)
    except Exception:
        stream = container.add_stream("h264", rate=fps)
    stream.width = width
    stream.height = height
    stream.pix_fmt = "yuv420p"

    try:
        for image in rgb_frames:
            if image.size != (width, height):
                image = image.resize((width, height), Image.Resampling.LANCZOS)
            frame = av.VideoFrame.from_image(image)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    finally:
        container.close()
