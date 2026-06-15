"""Hugging Face bucket relay for finished Small Cuts scenes.

The Space uses this as a read-only scene source. The private engine or a local
publisher writes finished scene manifests + media into an HF bucket; the Space
downloads those files into a temp cache and serves them through Gradio.
"""

from __future__ import annotations

import copy
import json
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, urlparse

import httpx

RELAY_BUCKET_ENV = "SMALL_CUTS_RELAY_BUCKET"
RELAY_PREFIX_ENV = "SMALL_CUTS_RELAY_PREFIX"
DEFAULT_RELAY_PREFIX = "relay"
RELAY_MANIFEST = "manifest.json"
RELAY_CACHE_DIR = Path(tempfile.gettempdir()) / "small-cuts-hf-relay"
GRADIO_FILE_ROUTE = "/gradio_api/file="
DEFAULT_SCENE_LIMIT = 60
MEDIA_KEYS = ("frame_url", "card_url", "audio_url", "clip_url")
PUBLISH_VISIBILITIES = frozenset({"shared", "public"})
HTTP_TIMEOUT_S = 20.0


class BucketFileSystem(Protocol):
    def cat(self, path: str) -> bytes: ...


class BucketRelayError(RuntimeError):
    """Raised when the bucket relay cannot read or hydrate its manifest."""


@dataclass(frozen=True)
class RelaySnapshot:
    path: Path
    scene_count: int
    manifest_path: Path


def gradio_file_url(path: str | Path) -> str:
    return f"{GRADIO_FILE_ROUTE}{quote(str(path))}"


def _normalize_prefix(prefix: str) -> str:
    return prefix.strip().strip("/")


def _safe_bucket_slug(bucket_id: str) -> str:
    return bucket_id.replace("/", "__")


class BucketSceneClient:
    """Read finished NarratedScene payloads from a Hugging Face bucket manifest."""

    base_url = ""
    readonly = True

    def __init__(
        self,
        bucket_id: str,
        *,
        prefix: str = DEFAULT_RELAY_PREFIX,
        fs: BucketFileSystem | None = None,
        cache_dir: str | Path | None = None,
        register_static_paths: Any | None = None,
    ) -> None:
        self.bucket_id = bucket_id.strip()
        if not self.bucket_id:
            raise ValueError("bucket_id is required")
        self.prefix = _normalize_prefix(prefix)
        self.root = f"hf://buckets/{self.bucket_id}"
        if self.prefix:
            self.root = f"{self.root}/{self.prefix}"
        self._fs = fs
        self.cache_dir = (
            Path(cache_dir)
            if cache_dir is not None
            else (RELAY_CACHE_DIR / _safe_bucket_slug(self.bucket_id))
        )
        if cache_dir is None and self.prefix:
            self.cache_dir = self.cache_dir / self.prefix
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if register_static_paths is not None:
            register_static_paths([self.cache_dir])

    @property
    def fs(self) -> BucketFileSystem:
        if self._fs is None:
            from huggingface_hub import HfFileSystem

            self._fs = HfFileSystem()
        return self._fs

    def list_scenes(self, limit: int = DEFAULT_SCENE_LIMIT) -> list[dict[str, Any]]:
        try:
            raw = self.fs.cat(f"{self.root}/{RELAY_MANIFEST}")
            manifest = json.loads(raw.decode("utf-8"))
            scenes = manifest.get("scenes", [])
            if not isinstance(scenes, list):
                raise ValueError("relay manifest scenes must be a list")
            return [self._hydrate_scene(scene) for scene in scenes[-limit:]]
        except FileNotFoundError:
            return []
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise BucketRelayError(f"could not read relay bucket {self.bucket_id}: {exc}") from exc

    def media_url(self, path: str | None) -> str | None:
        if not path:
            return None
        if path.startswith(("http://", "https://", "data:", GRADIO_FILE_ROUTE)):
            return path
        relative = self._relative_media_path(path)
        target = self.cache_dir / relative
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.fs.cat(f"{self.root}/{relative.as_posix()}"))
        return gradio_file_url(target)

    def _hydrate_scene(self, scene: dict[str, Any]) -> dict[str, Any]:
        hydrated = copy.deepcopy(scene)
        media = hydrated.get("media")
        if not isinstance(media, dict):
            hydrated["media"] = {}
            return hydrated
        for key in MEDIA_KEYS:
            media[key] = self.media_url(media.get(key))
        return hydrated

    def _relative_media_path(self, path: str) -> Path:
        value = path.strip().lstrip("/")
        if self.prefix and value.startswith(f"{self.prefix}/"):
            value = value[len(self.prefix) + 1 :]
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe bucket media path: {path}")
        return relative


def prepare_relay_snapshot(
    engine_url: str,
    output_dir: str | Path,
    *,
    limit: int = DEFAULT_SCENE_LIMIT,
    include_private: bool = False,
    client: httpx.Client | None = None,
) -> RelaySnapshot:
    """Stage a bucket-ready manifest + media snapshot from the private engine."""
    base_url = engine_url.rstrip("/")
    output = Path(output_dir)
    media_root = output / "media"
    output.mkdir(parents=True, exist_ok=True)
    media_root.mkdir(parents=True, exist_ok=True)
    close_client = client is None
    http = client or httpx.Client(timeout=HTTP_TIMEOUT_S)
    try:
        response = http.get(f"{base_url}/v1/scenes")
        response.raise_for_status()
        scenes = response.json().get("scenes", [])[-limit:]
        published = [
            _stage_scene_media(base_url, output, scene, http)
            for scene in scenes
            if _should_publish_scene(scene, include_private=include_private)
        ]
    finally:
        if close_client:
            http.close()
    manifest = {
        "contract_version": "1.1.0",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "source_engine": base_url,
        "scenes": published,
    }
    manifest_path = output / RELAY_MANIFEST
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return RelaySnapshot(output, len(published), manifest_path)


def _should_publish_scene(scene: dict[str, Any], *, include_private: bool) -> bool:
    if include_private:
        return True
    return scene.get("visibility") in PUBLISH_VISIBILITIES


def _stage_scene_media(
    engine_url: str,
    output_dir: Path,
    scene: dict[str, Any],
    client: httpx.Client,
) -> dict[str, Any]:
    staged = copy.deepcopy(scene)
    media = staged.get("media")
    if not isinstance(media, dict):
        staged["media"] = {}
        return staged
    scene_dir = _safe_path_segment(str(staged.get("scene_id") or "scene"))
    for key in MEDIA_KEYS:
        media[key] = _download_media(engine_url, output_dir, scene_dir, media.get(key), client)
    return staged


def _download_media(
    engine_url: str,
    output_dir: Path,
    scene_dir: str,
    url: str | None,
    client: httpx.Client,
) -> str | None:
    if not url:
        return None
    if url.startswith(("data:", GRADIO_FILE_ROUTE)):
        return None
    absolute = url if url.startswith(("http://", "https://")) else f"{engine_url}/{url.lstrip('/')}"
    relative = _relay_media_path(url, scene_dir)
    target = output_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    response = client.get(absolute)
    response.raise_for_status()
    target.write_bytes(response.content)
    return relative.as_posix()


def _relay_media_path(url: str, scene_dir: str) -> Path:
    parsed = urlparse(url)
    source_path = (parsed.path if parsed.scheme else url.split("?", 1)[0]).lstrip("/")
    if source_path.startswith("media/"):
        relative = Path(source_path)
    else:
        filename = _safe_path_segment(Path(source_path).name or "media.bin")
        relative = Path("media") / scene_dir / filename
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe relay media path: {url}")
    return relative


def _safe_path_segment(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "-" for ch in value)
    return cleaned.strip(".-") or "item"
