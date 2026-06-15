import json
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
