"""Phase 1 (Mid Cuts) token-isolation + same-origin proxy security tests.

CI-safe tests prove the read-token wiring, the fail-closed boot guard, and that a
PRIVATE bucket is served entirely same-origin (no cross-origin resolve URLs, no bucket
path leaked into client HTML). The gated LIVE tests (run once the real fine-grained
tokens + the macayaven/mid-cuts bucket exist) prove the cutover invariant: the
read-only token can read but cannot write.
"""

from __future__ import annotations

import json
import os

import pytest

from small_cuts import hf_relay
from test_contracts import GOLDEN


def _manifest_fs(scene):
    class FakeFs:
        def cat(self, path):
            if path.endswith("/manifest.json"):
                return json.dumps({"scenes": [scene]}).encode()
            return b"media-bytes"

    return FakeFs()


def _recording_hffilesystem(monkeypatch):
    import huggingface_hub

    created: dict[str, object] = {}

    class RecordingFs:
        def __init__(self, *args, **kwargs):
            created["token"] = kwargs.get("token", "MISSING")

    monkeypatch.setattr(huggingface_hub, "HfFileSystem", RecordingFs)
    return created


def test_fs_passes_read_token_to_hffilesystem(monkeypatch, tmp_path):
    created = _recording_hffilesystem(monkeypatch)
    monkeypatch.setenv(hf_relay.RELAY_READ_TOKEN_ENV, "read-only-xyz")

    client = hf_relay.BucketSceneClient("macayaven/mid-cuts", prefix="relay", cache_dir=tmp_path)
    _ = client.fs

    assert created["token"] == "read-only-xyz"


def test_fs_uses_no_token_by_default(monkeypatch, tmp_path):
    created = _recording_hffilesystem(monkeypatch)
    monkeypatch.delenv(hf_relay.RELAY_READ_TOKEN_ENV, raising=False)

    client = hf_relay.BucketSceneClient(
        "macayaven/small-cuts-scenes-dev", prefix="relay", cache_dir=tmp_path
    )
    _ = client.fs

    assert created["token"] is None


def test_boot_guard_refuses_direct_media_on_private_bucket(monkeypatch, tmp_path):
    monkeypatch.setenv(hf_relay.RELAY_BUCKET_PRIVATE_ENV, "1")

    with pytest.raises(hf_relay.BucketRelayError, match="private"):
        hf_relay.BucketSceneClient(
            "macayaven/mid-cuts",
            prefix="relay",
            cache_dir=tmp_path,
            direct_media_urls=True,
        )


def test_boot_guard_noop_on_public_bucket_in_direct_mode(monkeypatch, tmp_path):
    # The live macayaven/small-cuts Space posture: direct media, PUBLIC bucket, private flag
    # unset. The guard must NOT fire here, or it would crash the live Space at startup.
    monkeypatch.delenv(hf_relay.RELAY_BUCKET_PRIVATE_ENV, raising=False)

    client = hf_relay.BucketSceneClient(
        "macayaven/small-cuts-scenes-dev",
        prefix="relay",
        cache_dir=tmp_path,
        direct_media_urls=True,
    )

    assert client.direct_media_urls is True


def test_private_bucket_serves_clip_and_audio_same_origin(monkeypatch, tmp_path):
    scene = {
        **GOLDEN["narrated-scene.schema.json"],
        "media": {
            "frame_url": "media/scene-1/frame.jpg",
            "card_url": "media/scene-1/card.webp",
            "clip_url": "media/scene-1/clip.mp4",
            "audio_url": "media/scene-1/voice.wav",
        },
    }
    monkeypatch.setenv(hf_relay.RELAY_BUCKET_PRIVATE_ENV, "1")

    client = hf_relay.BucketSceneClient(
        "macayaven/mid-cuts",
        prefix="relay",
        fs=_manifest_fs(scene),
        cache_dir=tmp_path,
        direct_media_urls=False,
    )

    media = client.list_scenes()[0]["media"]
    for key in ("frame_url", "card_url", "clip_url", "audio_url"):
        assert media[key].startswith("/gradio_api/file="), key
        assert "huggingface.co/buckets" not in media[key], key


def test_boot_guard_fires_on_private_bucket_via_env_default(monkeypatch, tmp_path):
    # Production builds BucketSceneClient with NO direct_media_urls kwarg (viewer.py:2117);
    # on a real Space the env default (_default_direct_media_urls) resolves to direct mode.
    # The guard must fire on the RESOLVED value, not only on an explicit kwarg.
    monkeypatch.setenv("SPACE_ID", "macayaven/mid-cuts")
    monkeypatch.setenv(hf_relay.RELAY_BUCKET_ENV, "macayaven/mid-cuts")
    monkeypatch.delenv(hf_relay.RELAY_DIRECT_MEDIA_URLS_ENV, raising=False)
    monkeypatch.setenv(hf_relay.RELAY_BUCKET_PRIVATE_ENV, "1")

    with pytest.raises(hf_relay.BucketRelayError, match="private"):
        hf_relay.BucketSceneClient("macayaven/mid-cuts", prefix="relay", cache_dir=tmp_path)


def test_private_bucket_default_cache_path_emits_no_resolve_url(monkeypatch, tmp_path):
    # Exercise the PRODUCTION default-cache-dir derivation (no explicit cache_dir, as at
    # viewer.py:2117), rooted at tmp_path so the shared temp dir is not polluted. The
    # dangerous cross-origin resolve URL must never reach client HTML for a private bucket.
    scene = {
        **GOLDEN["narrated-scene.schema.json"],
        "media": {
            "frame_url": "media/scene-1/frame.jpg",
            "clip_url": "media/scene-1/clip.mp4",
            "audio_url": "media/scene-1/voice.wav",
        },
    }
    monkeypatch.setattr(hf_relay, "RELAY_CACHE_DIR", tmp_path)
    monkeypatch.setenv(hf_relay.RELAY_BUCKET_PRIVATE_ENV, "1")

    client = hf_relay.BucketSceneClient(
        "macayaven/mid-cuts", prefix="relay", fs=_manifest_fs(scene), direct_media_urls=False
    )

    media = client.list_scenes()[0]["media"]
    for key in ("frame_url", "clip_url", "audio_url"):
        assert "huggingface.co/buckets" not in media[key], key
        assert media[key].startswith("/gradio_api/file="), key


def test_boot_guard_error_does_not_leak_read_token(monkeypatch, tmp_path):
    # The boot-guard error is rendered to logs (and could surface to clients); it must name
    # only the bucket, never the read token value.
    monkeypatch.setenv(hf_relay.RELAY_READ_TOKEN_ENV, "super-secret-token")
    monkeypatch.setenv(hf_relay.RELAY_BUCKET_PRIVATE_ENV, "1")

    with pytest.raises(hf_relay.BucketRelayError) as excinfo:
        hf_relay.BucketSceneClient(
            "macayaven/mid-cuts", prefix="relay", cache_dir=tmp_path, direct_media_urls=True
        )

    assert "super-secret-token" not in str(excinfo.value)


# ── Gated LIVE cutover gate — run once the real tokens + bucket exist ──────────
# SMALL_CUTS_LIVE_TOKEN_TEST=1 SMALL_CUTS_RELAY_READ_TOKEN=<read-only token> \
#   uv run pytest tests/test_relay_token_isolation.py -k live
_live_only = pytest.mark.skipif(
    not os.environ.get("SMALL_CUTS_LIVE_TOKEN_TEST"),
    reason="needs SMALL_CUTS_LIVE_TOKEN_TEST=1 + SMALL_CUTS_RELAY_READ_TOKEN (live cutover gate)",
)


@_live_only
def test_live_read_token_can_read():
    from huggingface_hub import HfFileSystem

    bucket = os.environ.get("SMALL_CUTS_RELAY_BUCKET", "macayaven/mid-cuts")
    fs = HfFileSystem(token=os.environ["SMALL_CUTS_RELAY_READ_TOKEN"])
    # Positive control: a private bucket 401s anonymously, so a successful authenticated
    # listing proves the read token actually carries read scope (not a dud token).
    fs.ls(f"hf://buckets/{bucket}")


@_live_only
def test_live_read_token_cannot_write():
    from huggingface_hub import HfFileSystem
    from huggingface_hub.errors import HfHubHTTPError

    bucket = os.environ.get("SMALL_CUTS_RELAY_BUCKET", "macayaven/mid-cuts")
    fs = HfFileSystem(token=os.environ["SMALL_CUTS_RELAY_READ_TOKEN"])
    # The Xet bucket-write path wraps a denial in a builtin ConnectionError (an OSError), NOT
    # HfHubHTTPError — so catch broadly, then assert it is specifically a 401/403 authorization
    # denial (a stale-path or network error would not say "403 Forbidden"), keeping it from
    # false-passing on an incidental I/O failure.
    with (
        pytest.raises((HfHubHTTPError, OSError)) as excinfo,
        fs.open(f"hf://buckets/{bucket}/.isolation-probe", "wb") as handle,
    ):
        handle.write(b"read-only token must not be able to write")
    message = str(excinfo.value)
    status = getattr(getattr(excinfo.value, "response", None), "status_code", None)
    assert status in {401, 403} or "403" in message or "forbidden" in message.lower(), message
