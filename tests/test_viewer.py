"""P1 viewer: both build modes, the scene-poll formatter, and the engine client.

Engine mode is exercised against httpx.MockTransport — no live engine anywhere.
The NarratedScene fixture is the golden sample from test_contracts.py, so the
viewer's formatter is pinned to the same shape the contract suite enforces.
"""

import json
from datetime import datetime, timedelta, timezone

import gradio as gr
import httpx
import numpy as np
import pytest
from PIL import Image

from small_cuts import viewer
from test_contracts import GOLDEN

GOLDEN_SCENE = GOLDEN["narrated-scene.schema.json"]
ENGINE_URL = "http://engine.test:8077"
CREATED_AT = datetime(2026, 6, 12, 9, 30, 8, tzinfo=timezone.utc)  # the golden created_at


def make_image(width=64, height=48, color=(200, 200, 200)):
    return Image.new("RGB", (width, height), color)


def fake_client(handler) -> viewer.EngineClient:
    transport = httpx.MockTransport(handler)
    return viewer.EngineClient(ENGINE_URL, client=httpx.Client(transport=transport))


# -- build modes -----------------------------------------------------------------------


def test_build_viewer_app_upload_mode(monkeypatch):
    monkeypatch.delenv(viewer.ENGINE_URL_ENV, raising=False)
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)
    assert isinstance(viewer.build_viewer_app(), gr.Blocks)


def test_build_viewer_app_engine_mode_needs_no_live_engine(monkeypatch):
    # Port 9 is the discard port: any request at build time would fail loudly.
    monkeypatch.setenv(viewer.ENGINE_URL_ENV, "http://127.0.0.1:9")
    assert isinstance(viewer.build_viewer_app(), gr.Blocks)


# -- scene-poll formatter --------------------------------------------------------------


def test_format_stage_fresh_scene_is_live():
    now = CREATED_AT + timedelta(seconds=20)
    payload = viewer.format_stage(GOLDEN_SCENE, ENGINE_URL, now=now)
    assert payload["live"] is True
    assert payload["frame_src"] == f"{ENGINE_URL}/media/9f1c7e4a/frame.jpg"
    assert payload["audio_src"] == f"{ENGINE_URL}/media/9f1c7e4a/voice.wav"
    assert payload["caption"] == GOLDEN_SCENE["narration"]
    assert payload["title"] == "The Bicycle Is Mustard Yellow"
    assert payload["style_label"] == "Wes Anderson Symmetrist"
    assert payload["visibility"] == "private"
    assert payload["scene_id"] == GOLDEN_SCENE["scene_id"]


def test_format_stage_stale_scene_is_standby():
    now = CREATED_AT + timedelta(seconds=120)
    payload = viewer.format_stage(GOLDEN_SCENE, ENGINE_URL, now=now)
    assert payload["live"] is False


def test_format_stage_no_scene_is_off_air():
    payload = viewer.format_stage(None, ENGINE_URL)
    assert payload["live"] is False
    assert payload["frame_src"] is None
    assert payload["scene_id"] is None


def test_stage_html_shows_rec_state_and_escapes():
    live = viewer.render_stage_html("http://x/f.jpg", "a <script> walks in", live=True)
    assert "REC · LIVE" in live
    assert "<script>" not in live
    assert "&lt;script&gt;" in live
    stale = viewer.render_stage_html(None, "", live=False)
    assert "REC · STANDBY" in stale


def test_feed_renders_newest_first_for_column_reverse():
    entries = [
        viewer.feed_entry({"style_key": "noir", "narration": "first", "created_at": "x"}),
        viewer.feed_entry({"style_key": "trailer", "narration": "second", "created_at": "x"}),
    ]
    html = viewer.render_feed_html(entries)
    # column-reverse pins the scroll to the bottom, so newest must lead the DOM
    assert html.index("second") < html.index("first")
    assert "Noir Detective" in html and "Epic Trailer Voice" in html


# -- engine client + poll --------------------------------------------------------------


def test_visibility_patch_sends_right_body():
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={**GOLDEN_SCENE, "visibility": "shared"})

    scene = fake_client(handler).set_visibility(GOLDEN_SCENE["scene_id"], "shared")
    assert scene["visibility"] == "shared"
    (request,) = captured
    assert request.method == "PATCH"
    assert request.url.path == f"/v1/scenes/{GOLDEN_SCENE['scene_id']}"
    assert json.loads(request.content) == {"visibility": "shared"}


def test_poll_engine_renders_the_whole_page():
    def handler(request):
        assert request.url.path == "/v1/scenes"
        return httpx.Response(200, json={"scenes": [GOLDEN_SCENE]})

    now = CREATED_AT + timedelta(seconds=10)
    header, stage, feed, audio, shelf, scenes, current, playing, _vis = viewer.poll_engine(
        fake_client(handler), [], pinned_id=None, playing_id=None, now=now
    )
    assert "REC · LIVE" in stage
    assert f"{ENGINE_URL}/media/9f1c7e4a/frame.jpg" in stage
    assert "The Bicycle Is Mustard Yellow" in header
    assert "mustard yellow" in feed
    assert audio == f"{ENGINE_URL}/media/9f1c7e4a/voice.wav"
    assert shelf == [(f"{ENGINE_URL}/media/9f1c7e4a/card.webp", "The Bicycle Is Mustard Yellow")]
    assert scenes == [GOLDEN_SCENE]
    assert current == GOLDEN_SCENE["scene_id"]
    assert playing == GOLDEN_SCENE["scene_id"]


def test_poll_engine_stale_scene_reads_standby():
    def handler(request):
        return httpx.Response(200, json={"scenes": [GOLDEN_SCENE]})

    now = CREATED_AT + timedelta(minutes=10)
    _header, stage, *_rest = viewer.poll_engine(
        fake_client(handler), [], pinned_id=None, playing_id=None, now=now
    )
    assert "REC · STANDBY" in stage


def test_poll_engine_same_audio_not_restarted():
    def handler(request):
        return httpx.Response(200, json={"scenes": [GOLDEN_SCENE]})

    outputs = viewer.poll_engine(
        fake_client(handler),
        [GOLDEN_SCENE],
        pinned_id=None,
        playing_id=GOLDEN_SCENE["scene_id"],
        now=CREATED_AT,
    )
    audio, shelf = outputs[3], outputs[4]
    assert audio == gr.skip()  # already playing this scene: no restart
    assert shelf == gr.skip()  # shelf unchanged: no gallery re-render


def test_poll_engine_unreachable_engine_degrades_to_signal_lost():
    def handler(request):
        raise httpx.ConnectError("engine down")

    header, stage, *_rest = viewer.poll_engine(
        fake_client(handler), [GOLDEN_SCENE], pinned_id=None, playing_id=None
    )
    assert "Signal lost" in header
    assert stage == gr.skip()  # last picture stays up


# -- upload mode -----------------------------------------------------------------------


def test_go_live_handler_stages_a_scene(monkeypatch):
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)
    header, stage, feed, shelf, scenes, pinned = viewer._go_live_handler(
        make_image(), None, "noir", "", []
    )
    assert len(scenes) == 1
    scene = scenes[0]
    assert scene["style_key"] == "noir"
    assert scene["narration"]
    assert scene["title"] == viewer.derive_title(scene["narration"])
    assert scene["frame_src"].startswith("data:image/jpeg;base64,")
    assert scene["frame_src"] in stage
    assert "REC · LIVE" in stage
    assert scene["title"] in header
    assert "Noir Detective" in feed
    assert shelf == [(scene["card_thumb"], scene["title"])]
    assert pinned is None


def test_go_live_handler_without_moment_still_narrates(monkeypatch):
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)
    *_page, scenes, _pinned = viewer._go_live_handler(None, None, "deadpan", "", [])
    assert len(scenes) == 1
    assert "scene" in scenes[0]["narration"].lower()  # the empty-stage easter egg


def test_go_live_handler_appends_to_session_shelf(monkeypatch):
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)
    *_page, scenes, _pinned = viewer._go_live_handler(make_image(), None, "noir", "", [])
    *_page, scenes, _pinned = viewer._go_live_handler(make_image(), None, "trailer", "", scenes)
    assert [s["style_key"] for s in scenes] == ["noir", "trailer"]


def test_voice_handler_speaks_current_scene(monkeypatch):
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)
    monkeypatch.delenv("SMALL_CUTS_TTS_BACKEND", raising=False)
    *_page, scenes, _pinned = viewer._go_live_handler(make_image(), None, "noir", "", [])
    result = viewer._voice_handler(scenes, None)
    assert result is not None
    sample_rate, audio = result
    assert sample_rate > 0
    assert isinstance(audio, np.ndarray) and audio.size > 0
    assert viewer._voice_handler([], None) is None


def test_voice_handler_prefers_pinned_scene(monkeypatch):
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)
    first = {"scene_id": "a", "narration": "alpha"}
    second = {"scene_id": "b", "narration": "beta"}
    assert viewer._current_scene([first, second], "a") is first
    assert viewer._current_scene([first, second], None) is second
    assert viewer._current_scene([first, second], "missing") is second


@pytest.mark.parametrize(
    ("created_at", "fresh"),
    [
        (CREATED_AT.isoformat(), True),
        ((CREATED_AT - timedelta(minutes=5)).isoformat(), False),
        ("2026-06-12T09:30:08Z", True),  # engine emits Z-suffixed timestamps
        (None, False),
        ("not-a-date", False),
    ],
)
def test_is_fresh(created_at, fresh):
    now = CREATED_AT + timedelta(seconds=30)
    assert viewer.is_fresh(created_at, now=now) is fresh
