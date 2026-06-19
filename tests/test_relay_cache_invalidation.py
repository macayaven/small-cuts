"""Phase 4 (Mid Cuts): the push-not-poll cache-bust.

A relay-scene SSE push triggers a single re-read of the bucket. ``BucketSceneClient.list_scenes``
caches the hydrated scene list for ``MANIFEST_CACHE_TTL_S``; without busting that cache a fresh
publish within the TTL would be invisible to the just-pushed browser. ``invalidate_cache()`` lets
the push path force the next read to be fresh, while every other (non-push) read stays cached.
"""

from __future__ import annotations

import json
from pathlib import Path

from small_cuts import hf_relay
from test_contracts import GOLDEN


def _scene(scene_id: str) -> dict:
    return {
        **GOLDEN["narrated-scene.schema.json"],
        "scene_id": scene_id,
        "media": {"frame_url": f"media/{scene_id}/frame.jpg"},
    }


class _MutableManifestFs:
    """Fake bucket fs whose manifest contents can change between reads (no glob => no uploads/)."""

    def __init__(self, scenes: list[dict]) -> None:
        self.scenes = list(scenes)

    def cat(self, path: str) -> bytes:
        if path.endswith("/manifest.json"):
            return json.dumps({"scenes": self.scenes}).encode()
        return b"media-bytes"


def _client(fs: _MutableManifestFs, tmp_path: Path) -> hf_relay.BucketSceneClient:
    return hf_relay.BucketSceneClient(
        "macayaven/mid-cuts", prefix="relay", fs=fs, cache_dir=tmp_path, direct_media_urls=False
    )


def test_list_scenes_serves_cache_within_ttl(tmp_path):
    fs = _MutableManifestFs([_scene("a")])
    client = _client(fs, tmp_path)

    assert {s["scene_id"] for s in client.list_scenes()} == {"a"}
    fs.scenes = [_scene("a"), _scene("b")]
    # Within MANIFEST_CACHE_TTL_S the cached (stale) list is returned — the existing behavior.
    assert {s["scene_id"] for s in client.list_scenes()} == {"a"}


def test_invalidate_cache_forces_fresh_read(tmp_path):
    fs = _MutableManifestFs([_scene("a")])
    client = _client(fs, tmp_path)

    client.list_scenes()  # populate the cache
    fs.scenes = [_scene("a"), _scene("b")]
    client.invalidate_cache()
    # After invalidation the next read re-globs the bucket and sees the freshly published scene.
    assert {s["scene_id"] for s in client.list_scenes()} == {"a", "b"}
