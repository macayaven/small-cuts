import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from small_cuts import hf_relay
from test_contracts import GOLDEN

ENGINE_URL = "http://engine.test:8077"


def test_prepare_relay_snapshot_writes_manifest_and_media(tmp_path):
    scene = {
        **GOLDEN["narrated-scene.schema.json"],
        "visibility": "public",
        "media": {
            "frame_url": "/media/9f1c7e4a/frame.jpg",
            "card_url": "/media/9f1c7e4a/card.webp",
            "audio_url": "/media/9f1c7e4a/voice.wav",
            "clip_url": "/media/9f1c7e4a/clip.mp4",
        },
    }
    served = {
        "/v1/scenes": httpx.Response(200, json={"scenes": [scene]}),
        "/media/9f1c7e4a/frame.jpg": httpx.Response(200, content=b"frame"),
        "/media/9f1c7e4a/card.webp": httpx.Response(200, content=b"card"),
        "/media/9f1c7e4a/voice.wav": httpx.Response(200, content=b"voice"),
        "/media/9f1c7e4a/clip.mp4": httpx.Response(200, content=b"clip"),
    }

    def handler(request):
        return served[request.url.path]

    snapshot = hf_relay.prepare_relay_snapshot(
        ENGINE_URL,
        tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert snapshot.scene_count == 1
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    (published,) = manifest["scenes"]
    assert published["media"]["frame_url"] == "media/9f1c7e4a/frame.jpg"
    assert (tmp_path / "media/9f1c7e4a/frame.jpg").read_bytes() == b"frame"
    assert (tmp_path / "media/9f1c7e4a/voice.wav").read_bytes() == b"voice"
    assert manifest["source_engine"] == ENGINE_URL


def test_prepare_relay_snapshot_skips_private_scenes_by_default(tmp_path):
    private_scene = {**GOLDEN["narrated-scene.schema.json"], "visibility": "private"}

    def handler(request):
        assert request.url.path == "/v1/scenes"
        return httpx.Response(200, json={"scenes": [private_scene]})

    snapshot = hf_relay.prepare_relay_snapshot(
        ENGINE_URL,
        tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert snapshot.scene_count == 0
    assert json.loads((tmp_path / "manifest.json").read_text())["scenes"] == []


def test_prepare_relay_snapshot_can_include_private_scenes(tmp_path):
    private_scene = {
        **GOLDEN["narrated-scene.schema.json"],
        "visibility": "private",
        "media": {"frame_url": "/media/9f1c7e4a/frame.jpg"},
    }

    def handler(request):
        if request.url.path == "/v1/scenes":
            return httpx.Response(200, json={"scenes": [private_scene]})
        assert request.url.path == "/media/9f1c7e4a/frame.jpg"
        return httpx.Response(200, content=b"frame")

    snapshot = hf_relay.prepare_relay_snapshot(
        ENGINE_URL,
        tmp_path,
        include_private=True,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert snapshot.scene_count == 1
    assert (tmp_path / "media/9f1c7e4a/frame.jpg").exists()


def test_prepare_relay_snapshot_can_mark_scene_source(tmp_path):
    scene = {
        **GOLDEN["narrated-scene.schema.json"],
        "visibility": "public",
        "media": {"frame_url": "/media/9f1c7e4a/frame.jpg"},
    }

    def handler(request):
        if request.url.path == "/v1/scenes":
            return httpx.Response(200, json={"scenes": [scene]})
        assert request.url.path == "/media/9f1c7e4a/frame.jpg"
        return httpx.Response(200, content=b"frame")

    hf_relay.prepare_relay_snapshot(
        ENGINE_URL,
        tmp_path,
        source="glasses",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    (published,) = manifest["scenes"]
    assert published["source"] == "glasses"
    assert published["source_icon"] == "glasses"


def test_bucket_scene_client_caches_manifest_and_media(tmp_path):
    scene = {
        **GOLDEN["narrated-scene.schema.json"],
        "media": {"frame_url": "media/scene-1/frame.jpg"},
    }

    class FakeFs:
        def __init__(self):
            self.calls = []

        def cat(self, path):
            self.calls.append(path)
            if path.endswith("/manifest.json"):
                return json.dumps({"scenes": [scene]}).encode()
            if path.endswith("/media/scene-1/frame.jpg"):
                return b"frame"
            raise FileNotFoundError(path)

    fs = FakeFs()
    client = hf_relay.BucketSceneClient(
        "macayaven/small-cuts-scenes-dev",
        prefix="relay",
        fs=fs,
        cache_dir=tmp_path,
    )

    assert client.list_scenes()[0]["media"]["frame_url"].startswith("/gradio_api/file=")
    assert client.list_scenes()[0]["media"]["frame_url"].startswith("/gradio_api/file=")

    assert fs.calls.count("hf://buckets/macayaven/small-cuts-scenes-dev/relay/manifest.json") == 1
    assert (
        fs.calls.count("hf://buckets/macayaven/small-cuts-scenes-dev/relay/media/scene-1/frame.jpg")
        == 1
    )


def test_bucket_scene_client_can_use_hf_resolve_media_urls(tmp_path):
    scene = {
        **GOLDEN["narrated-scene.schema.json"],
        "media": {
            "frame_url": "media/scene 1/frame.jpg",
            "clip_url": "media/scene 1/clip.mp4",
        },
    }

    class FakeFs:
        def cat(self, path):
            if path.endswith("/manifest.json"):
                return json.dumps({"scenes": [scene]}).encode()
            raise AssertionError(f"unexpected media fetch through fs: {path}")

    client = hf_relay.BucketSceneClient(
        "macayaven/small-cuts-scenes-dev",
        prefix="relay",
        fs=FakeFs(),
        cache_dir=tmp_path,
        direct_media_urls=True,
    )

    media = client.list_scenes()[0]["media"]

    assert media["clip_url"] == (
        "https://huggingface.co/buckets/macayaven/small-cuts-scenes-dev"
        "/resolve/relay/media/scene%201/clip.mp4"
    )
    assert media["frame_url"] == (
        "https://huggingface.co/buckets/macayaven/small-cuts-scenes-dev"
        "/resolve/relay/media/scene%201/frame.jpg"
    )


def test_bucket_scene_client_discovers_modal_upload_scene_files(tmp_path):
    relay_scene = {
        **GOLDEN["narrated-scene.schema.json"],
        "scene_id": "relay-scene",
        "created_at": "2026-06-16T10:00:00+00:00",
        "media": {"frame_url": "media/relay-scene/frame.jpg"},
    }
    upload_scene = {
        **GOLDEN["narrated-scene.schema.json"],
        "scene_id": "modal-upload",
        "created_at": "2026-06-17T05:48:34+00:00",
        "source": "upload",
        "media": {"frame_url": "uploads/modal-upload/media/frame.jpg"},
    }

    class FakeFs:
        def __init__(self):
            self.root = "hf://buckets/macayaven/small-cuts-scenes-dev/relay"

        def cat(self, path):
            if path == f"{self.root}/manifest.json":
                return json.dumps({"scenes": [relay_scene]}).encode()
            if path == f"{self.root}/uploads/modal-upload/scene.json":
                return json.dumps(upload_scene).encode()
            if path.endswith("/media/relay-scene/frame.jpg"):
                return b"relay-frame"
            if path.endswith("/uploads/modal-upload/media/frame.jpg"):
                return b"upload-frame"
            raise FileNotFoundError(path)

        def glob(self, pattern):
            assert pattern == f"{self.root}/uploads/*/scene.json"
            return [f"{self.root}/uploads/modal-upload/scene.json"]

    client = hf_relay.BucketSceneClient(
        "macayaven/small-cuts-scenes-dev",
        prefix="relay",
        fs=FakeFs(),
        cache_dir=tmp_path,
    )

    scenes = client.list_scenes()

    assert [scene["scene_id"] for scene in scenes] == ["relay-scene", "modal-upload"]
    assert scenes[1]["source"] == "upload"
    assert scenes[1]["media"]["frame_url"].startswith("/gradio_api/file=")


def test_bucket_scene_client_reads_uploads_from_configured_bucket_mount(monkeypatch, tmp_path):
    mount = tmp_path / "bucket"
    relay_root = mount / "relay"
    upload_root = relay_root / "uploads" / "modal-upload"
    media_path = upload_root / "media" / "frame.jpg"
    media_path.parent.mkdir(parents=True)
    media_path.write_bytes(b"frame")
    (relay_root / "manifest.json").write_text(json.dumps({"scenes": []}))
    (upload_root / "scene.json").write_text(
        json.dumps(
            {
                **GOLDEN["narrated-scene.schema.json"],
                "scene_id": "modal-upload",
                "source": "upload",
                "media": {"frame_url": "uploads/modal-upload/media/frame.jpg"},
            }
        )
    )
    monkeypatch.setenv("SMALL_CUTS_BUCKET_MOUNT_PATH", str(mount))

    class UnusedFs:
        def cat(self, path):
            raise AssertionError(f"unexpected bucket cat: {path}")

        def glob(self, pattern):
            raise AssertionError(f"unexpected bucket glob: {pattern}")

    client = hf_relay.BucketSceneClient(
        "macayaven/small-cuts-scenes-dev",
        prefix="relay",
        fs=UnusedFs(),
        cache_dir=tmp_path / "cache",
    )

    scenes = client.list_scenes()

    assert [scene["scene_id"] for scene in scenes] == ["modal-upload"]
    assert scenes[0]["media"]["frame_url"] == hf_relay.gradio_file_url(media_path)


def test_bucket_scene_client_serializes_concurrent_media_cache_writes(tmp_path):
    class FakeFs:
        def __init__(self):
            self.calls = 0

        def cat(self, path):
            self.calls += 1
            time.sleep(0.05)
            return b"frame"

    fs = FakeFs()
    client = hf_relay.BucketSceneClient(
        "macayaven/small-cuts-scenes-dev",
        prefix="relay",
        fs=fs,
        cache_dir=tmp_path,
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        urls = list(pool.map(client.media_url, ["media/scene-1/frame.jpg"] * 2))

    assert urls[0] == urls[1]
    assert fs.calls == 1
    assert (tmp_path / "media/scene-1/frame.jpg").read_bytes() == b"frame"


def test_bucket_scene_client_skips_scene_with_missing_media_instead_of_blanking_all(tmp_path):
    broken = {
        **GOLDEN["narrated-scene.schema.json"],
        "scene_id": "broken",
        "media": {"frame_url": "media/broken/frame.jpg"},
    }
    good = {
        **GOLDEN["narrated-scene.schema.json"],
        "scene_id": "good",
        "media": {"frame_url": "media/good/frame.jpg"},
    }

    class FakeFs:
        def cat(self, path):
            if path.endswith("/manifest.json"):
                return json.dumps({"scenes": [broken, good]}).encode()
            if path.endswith("/media/good/frame.jpg"):
                return b"frame"
            raise FileNotFoundError(path)

    client = hf_relay.BucketSceneClient(
        "macayaven/small-cuts-scenes-dev",
        prefix="relay",
        fs=FakeFs(),
        cache_dir=tmp_path,
    )

    assert [scene["scene_id"] for scene in client.list_scenes()] == ["good"]


def test_bucket_scene_client_prunes_old_cache_files_after_media_write(tmp_path):
    old = tmp_path / "media/old/frame.jpg"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old-old-old")
    old_mtime = time.time() - 120
    os.utime(old, (old_mtime, old_mtime))

    class FakeFs:
        def cat(self, path):
            return b"fresh"

    client = hf_relay.BucketSceneClient(
        "macayaven/small-cuts-scenes-dev",
        prefix="relay",
        fs=FakeFs(),
        cache_dir=tmp_path,
        cache_max_bytes=6,
    )

    client.media_url("media/new/frame.jpg")

    assert not old.exists()
    assert (tmp_path / "media/new/frame.jpg").read_bytes() == b"fresh"
