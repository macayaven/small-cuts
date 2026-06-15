import json

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
