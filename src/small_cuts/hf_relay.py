"""Hugging Face bucket relay for finished Small Cuts scenes.

The Space uses this as a read-only scene source. The private engine or a local
publisher writes finished scene manifests + media into an HF bucket; the Space
downloads those files into a temp cache and serves them through Gradio.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, urlparse

import httpx

from .persistence import bucket_mount_path

RELAY_BUCKET_ENV = "SMALL_CUTS_RELAY_BUCKET"
RELAY_PREFIX_ENV = "SMALL_CUTS_RELAY_PREFIX"
RELAY_DIRECT_MEDIA_URLS_ENV = "SMALL_CUTS_RELAY_DIRECT_MEDIA_URLS"
RELAY_READ_TOKEN_ENV = "SMALL_CUTS_RELAY_READ_TOKEN"
RELAY_BUCKET_PRIVATE_ENV = "SMALL_CUTS_RELAY_BUCKET_PRIVATE"
DEFAULT_RELAY_PREFIX = "relay"
RELAY_MANIFEST = "manifest.json"
RELAY_CACHE_DIR = Path(tempfile.gettempdir()) / "small-cuts-hf-relay"
GRADIO_FILE_ROUTE = "/gradio_api/file="
DEFAULT_SCENE_LIMIT = 60
MEDIA_KEYS = ("frame_url", "card_url", "audio_url", "clip_url")
SHELF_MEDIA_KEYS = ("frame_url", "card_url")
PUBLISH_VISIBILITIES = frozenset({"shared", "public"})
HTTP_TIMEOUT_S = 20.0
MANIFEST_CACHE_TTL_S = 5.0
RELAY_CACHE_MAX_BYTES = 512 * 1024 * 1024

_MISSING_SHELF_MEDIA_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 180">'
    '<rect width="320" height="180" fill="#101014"/>'
    '<rect x="20" y="20" width="280" height="140" rx="10" fill="none" '
    'stroke="#2f2f38" stroke-width="2" stroke-dasharray="8 8"/>'
    '<text x="160" y="92" fill="#d4af37" font-family="monospace" '
    'font-size="18" text-anchor="middle">ROLLING</text>'
    '<text x="160" y="118" fill="#8a8894" font-family="monospace" '
    'font-size="12" text-anchor="middle">media still landing</text>'
    "</svg>"
)
MISSING_SHELF_MEDIA_PLACEHOLDER = f"data:image/svg+xml,{quote(_MISSING_SHELF_MEDIA_SVG, safe='')}"


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
        manifest_cache_ttl_s: float = MANIFEST_CACHE_TTL_S,
        cache_max_bytes: int = RELAY_CACHE_MAX_BYTES,
        direct_media_urls: bool | None = None,
    ) -> None:
        self.bucket_id = bucket_id.strip()
        if not self.bucket_id:
            raise ValueError("bucket_id is required")
        self.prefix = _normalize_prefix(prefix)
        self.root = f"hf://buckets/{self.bucket_id}"
        if self.prefix:
            self.root = f"{self.root}/{self.prefix}"
        self._fs = fs
        mount = bucket_mount_path()
        self.bucket_mount_path = mount.expanduser().resolve() if mount is not None else None
        self.mounted_root = (
            self.bucket_mount_path / self.prefix
            if self.bucket_mount_path is not None and self.prefix
            else self.bucket_mount_path
        )
        self.cache_dir = (
            Path(cache_dir)
            if cache_dir is not None
            else (RELAY_CACHE_DIR / _safe_bucket_slug(self.bucket_id))
        )
        if cache_dir is None and self.prefix:
            self.cache_dir = self.cache_dir / self.prefix
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if register_static_paths is not None:
            static_paths = [self.cache_dir]
            if self.bucket_mount_path is not None:
                static_paths.append(self.bucket_mount_path)
            register_static_paths(static_paths)
        self.manifest_cache_ttl_s = manifest_cache_ttl_s
        self.cache_max_bytes = cache_max_bytes
        self.direct_media_urls = (
            _default_direct_media_urls() if direct_media_urls is None else bool(direct_media_urls)
        )
        self._read_token = os.environ.get(RELAY_READ_TOKEN_ENV, "").strip() or None
        self.bucket_private = _env_flag(RELAY_BUCKET_PRIVATE_ENV)
        if self.bucket_private and self.direct_media_urls:
            raise BucketRelayError(
                f"refusing to start: direct-media (resolve) URLs against private bucket "
                f"{self.bucket_id} would 404 for anonymous clients and leak the bucket path "
                f"into client HTML; set {RELAY_DIRECT_MEDIA_URLS_ENV}=0 to serve same-origin"
            )
        self._manifest_lock = threading.Lock()
        self._media_lock = threading.Lock()
        self._manifest_cache: tuple[float, list[dict[str, Any]]] | None = None
        self._prune_cache()

    @property
    def fs(self) -> BucketFileSystem:
        if self._fs is None:
            from huggingface_hub import HfFileSystem

            self._fs = HfFileSystem(token=self._read_token)
        return self._fs

    def list_scenes(self, limit: int = DEFAULT_SCENE_LIMIT) -> list[dict[str, Any]]:
        with self._manifest_lock:
            now = time.monotonic()
            if (
                self._manifest_cache is not None
                and now - self._manifest_cache[0] < self.manifest_cache_ttl_s
            ):
                return copy.deepcopy(self._manifest_cache[1][-limit:])
            try:
                raw = self._read_manifest()
                scenes = self._manifest_scenes(raw) if raw is not None else []
                hydrated = []
                for scene in scenes:
                    try:
                        hydrated.append(self._hydrate_scene(scene, keys=self._list_media_keys()))
                    except FileNotFoundError:
                        continue
                uploaded = self._uploaded_scenes()
                hydrated = _merge_bucket_scenes(hydrated, uploaded)
                self._manifest_cache = (now, hydrated)
                return copy.deepcopy(hydrated[-limit:])
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise BucketRelayError(
                    f"could not read relay bucket {self.bucket_id}: {exc}"
                ) from exc

    def invalidate_cache(self) -> None:
        """Drop the cached scene list so the next ``list_scenes`` re-reads the bucket.

        The relay-scene push path calls this so a freshly published cut is visible immediately, even
        within ``MANIFEST_CACHE_TTL_S`` of a prior read; non-push reads keep using the cache.
        """
        with self._manifest_lock:
            self._manifest_cache = None

    def _manifest_scenes(self, raw: bytes) -> list[dict[str, Any]]:
        manifest = json.loads(raw.decode("utf-8"))
        scenes = manifest.get("scenes", [])
        if not isinstance(scenes, list):
            raise ValueError("relay manifest scenes must be a list")
        return scenes

    def _read_manifest(self) -> bytes | None:
        local_manifest = self._mounted_file(RELAY_MANIFEST)
        if local_manifest is not None and local_manifest.is_file():
            return local_manifest.read_bytes()
        try:
            return self.fs.cat(f"{self.root}/{RELAY_MANIFEST}")
        except FileNotFoundError:
            return None

    def _uploaded_scenes(self) -> list[dict[str, Any]]:
        mounted_paths = self._mounted_upload_scene_paths()
        if mounted_paths is not None:
            uploaded = []
            for scene_path in mounted_paths:
                scene = json.loads(scene_path.read_bytes().decode("utf-8"))
                if isinstance(scene, dict):
                    uploaded.append(self._hydrate_scene(scene, keys=self._list_media_keys()))
            return uploaded
        glob = getattr(self.fs, "glob", None)
        if glob is None:
            return []
        # fsspec caches directory listings for the life of the fs object, so a newly published
        # uploads/<id>/scene.json would never be globbed (the v2 manifest-less path) until the fs is
        # recreated. Bust the listing cache before globbing. The manifest (cat) path is unaffected,
        # so the live Space's manifest-based relay is unchanged.
        invalidate_listings = getattr(self.fs, "invalidate_cache", None)
        if invalidate_listings is not None:
            invalidate_listings()
        try:
            scene_paths = glob(f"{self.root}/uploads/*/scene.json")
        except FileNotFoundError:
            return []
        uploaded = []
        for scene_path in sorted(str(path) for path in scene_paths):
            try:
                raw = self.fs.cat(scene_path)
                scene = json.loads(raw.decode("utf-8"))
                if isinstance(scene, dict):
                    uploaded.append(self._hydrate_scene(scene, keys=self._list_media_keys()))
            except FileNotFoundError:
                continue
        return uploaded

    def media_url(self, path: str | None) -> str | None:
        if not path:
            return None
        if path.startswith(("http://", "https://", "data:", GRADIO_FILE_ROUTE)):
            return path
        relative = self._relative_media_path(path)
        if self.direct_media_urls:
            return self._hf_resolve_url(relative)
        mounted = self._mounted_file(relative)
        if mounted is not None and mounted.is_file():
            return gradio_file_url(mounted)
        target = self.cache_dir / relative
        with self._media_lock:
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(f".{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
                try:
                    tmp.write_bytes(self.fs.cat(f"{self.root}/{relative.as_posix()}"))
                    tmp.replace(target)
                finally:
                    tmp.unlink(missing_ok=True)
                self._prune_cache(protected=target)
        return gradio_file_url(target)

    def _hf_resolve_url(self, relative: str | Path) -> str:
        path = Path(relative).as_posix()
        if self.prefix:
            path = f"{self.prefix}/{path}"
        return (
            f"https://huggingface.co/buckets/{quote(self.bucket_id, safe='/')}"
            f"/resolve/{quote(path, safe='/')}"
        )

    def _hydrate_scene(
        self, scene: dict[str, Any], *, keys: tuple[str, ...] = MEDIA_KEYS
    ) -> dict[str, Any]:
        hydrated = copy.deepcopy(scene)
        media = hydrated.get("media")
        if not isinstance(media, dict):
            hydrated["media"] = {}
            return hydrated
        for key in keys:
            try:
                media[key] = self.media_url(media.get(key))
            except FileNotFoundError:
                media[key] = self._missing_media_url(key)
        return hydrated

    def _missing_media_url(self, key: str) -> str | None:
        if key in SHELF_MEDIA_KEYS:
            return MISSING_SHELF_MEDIA_PLACEHOLDER
        return None

    def _list_media_keys(self) -> tuple[str, ...]:
        # A private bucket is proxied entirely same-origin (clip + audio too, not just the
        # shelf thumbnails) so Safari can load and seek the video; existing engine/upload
        # proxy modes keep serving only the shelf keys (media arrives via a mount).
        if self.direct_media_urls or self.bucket_private:
            return MEDIA_KEYS
        return SHELF_MEDIA_KEYS

    def _relative_media_path(self, path: str) -> Path:
        value = path.strip().lstrip("/")
        if self.prefix and value.startswith(f"{self.prefix}/"):
            value = value[len(self.prefix) + 1 :]
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe bucket media path: {path}")
        return relative

    def _mounted_file(self, relative: str | Path) -> Path | None:
        if self.mounted_root is None:
            return None
        path = self.mounted_root / Path(relative)
        if path.is_absolute() and self.mounted_root not in [path, *path.parents]:
            raise ValueError(f"unsafe mounted bucket path: {relative}")
        return path

    def _mounted_upload_scene_paths(self) -> list[Path] | None:
        if self.mounted_root is None or not self.mounted_root.exists():
            return None
        uploads_dir = self.mounted_root / "uploads"
        if not uploads_dir.exists():
            return []
        return sorted(uploads_dir.glob("*/scene.json"))

    def _prune_cache(self, protected: Path | None = None) -> None:
        if self.cache_max_bytes <= 0 or not self.cache_dir.exists():
            return
        protected_resolved = protected.resolve() if protected is not None else None
        files = [path for path in self.cache_dir.rglob("*") if path.is_file()]
        total = sum(path.stat().st_size for path in files)
        if total <= self.cache_max_bytes:
            return
        for path in sorted(files, key=lambda item: item.stat().st_mtime):
            if protected_resolved is not None and path.resolve() == protected_resolved:
                continue
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            total -= size
            if total <= self.cache_max_bytes:
                break


def prepare_relay_snapshot(
    engine_url: str,
    output_dir: str | Path,
    *,
    limit: int = DEFAULT_SCENE_LIMIT,
    include_private: bool = False,
    source: str | None = None,
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
            _stage_scene_media(base_url, output, scene, http, source=source)
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
    *,
    source: str | None = None,
) -> dict[str, Any]:
    staged = copy.deepcopy(scene)
    if source:
        staged["source"] = source
        staged["source_icon"] = source
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


def _merge_bucket_scenes(
    manifest_scenes: list[dict[str, Any]], uploaded_scenes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for scene in [*manifest_scenes, *uploaded_scenes]:
        scene_id = str(scene.get("scene_id") or "")
        if scene_id:
            by_id[scene_id] = scene
    return sorted(
        by_id.values(),
        key=lambda scene: (str(scene.get("created_at") or ""), str(scene.get("scene_id") or "")),
    )


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _default_direct_media_urls() -> bool:
    configured = os.environ.get(RELAY_DIRECT_MEDIA_URLS_ENV)
    if configured is not None and configured.strip():
        return _env_flag(RELAY_DIRECT_MEDIA_URLS_ENV)
    return bool(
        os.environ.get("SPACE_ID", "").strip() and os.environ.get(RELAY_BUCKET_ENV, "").strip()
    )
