"""P1 viewer: both build modes, the scene-poll formatter, and the engine client.

Engine mode is exercised against httpx.MockTransport — no live engine anywhere.
The NarratedScene fixture is the golden sample from test_contracts.py, so the
viewer's formatter is pinned to the same shape the contract suite enforces.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

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


def test_build_viewer_app_bucket_relay_mode_needs_no_live_engine(monkeypatch):
    monkeypatch.delenv(viewer.ENGINE_URL_ENV, raising=False)
    monkeypatch.setenv(viewer.RELAY_BUCKET_ENV, "build-small-hackathon/small-cuts-scenes")
    assert isinstance(viewer.build_viewer_app(), gr.Blocks)


def test_upload_sandbox_requires_modal_url(monkeypatch):
    monkeypatch.setenv("SMALL_CUTS_ENABLE_UPLOAD_SANDBOX", "1")
    monkeypatch.delenv("SMALL_CUTS_MODAL_API_URL", raising=False)

    assert viewer.upload_sandbox_enabled() is False

    monkeypatch.setenv("SMALL_CUTS_MODAL_API_URL", "https://example.modal.run")

    assert viewer.upload_sandbox_enabled() is True


def test_upload_requires_hf_profile():
    with pytest.raises(gr.Error, match="Sign in"):
        viewer._require_upload_profile(None)


def test_upload_profile_uses_hf_username():
    profile = SimpleNamespace(name="Alice Example", username="alice")

    assert viewer._require_upload_profile(profile) == "alice"


def test_uploaded_scene_is_preserved_in_engine_state():
    upload_scene = {
        "scene_id": "modal-upload-1",
        "title": "A Finished Judge Upload",
        "source": "upload",
    }

    state = viewer._pack_engine_ui_state(
        scenes=[],
        pinned_id=None,
        current_id=None,
        playing_id=None,
        previous={"upload_scene": upload_scene},
    )

    assert state["upload_scene"]["scene_id"] == "modal-upload-1"


def test_upload_video_cap_defaults_to_sixty_seconds(monkeypatch):
    monkeypatch.delenv("SMALL_CUTS_UPLOAD_MAX_SECONDS", raising=False)

    assert viewer.upload_max_seconds() == 60.0


def test_modal_scene_can_drive_uploaded_stage():
    scene = {
        "scene_id": "modal-1",
        "title": "A sentence.",
        "narration": "A sentence.",
        "style_key": "deadpan",
        "created_at": "2026-06-15T12:00:00+00:00",
        "media": {
            "frame_url": "/gradio_api/file=/tmp/frame.jpg",
            "clip_url": "/gradio_api/file=/tmp/clip.mp4",
            "audio_url": "/gradio_api/file=/tmp/voice.wav",
        },
        "duration": 12.5,
    }

    payload = viewer.format_stage(scene)

    assert payload["clip_src"].endswith("clip.mp4")
    assert payload["audio_src"].endswith("voice.wav")
    assert payload["duration"] == 12.5


def test_format_stage_marks_source_icons():
    scene = {**GOLDEN_SCENE, "source": "glasses"}
    upload_scene = {**GOLDEN_SCENE, "source": "upload"}

    glasses_payload = viewer.format_stage(scene, ENGINE_URL)
    upload_payload = viewer.format_stage(upload_scene, ENGINE_URL)

    assert glasses_payload["source_icon"] == "glasses"
    assert upload_payload["source_icon"] == "upload"


def test_submit_modal_upload_rejects_over_duration(monkeypatch):
    monkeypatch.setenv("SMALL_CUTS_UPLOAD_MAX_SECONDS", "60")
    monkeypatch.setattr(viewer, "_video_duration_s", lambda _path: 61.0)

    with pytest.raises(gr.Error, match="up to 60 seconds"):
        viewer._submit_modal_upload(
            "clip.mp4",
            "deadpan",
            "",
            viewer._pack_engine_ui_state([], None, None, None),
            SimpleNamespace(name="Alice Example", username="alice"),
            fake_client(lambda _request: httpx.Response(200, json={"scenes": []})),
        )


def test_submit_modal_upload_pins_returned_scene(monkeypatch):
    scene = {
        "scene_id": "modal-1",
        "title": "A Modal Scene",
        "narration": "The clip now has a real voice.",
        "style_key": "deadpan",
        "created_at": "2026-06-15T12:00:00+00:00",
        "visibility": "public",
        "media": {
            "frame_url": "uploads/modal-1/media/frame.jpg",
            "card_url": "uploads/modal-1/media/card.webp",
            "clip_url": "uploads/modal-1/media/clip.mp4",
            "audio_url": "uploads/modal-1/media/voice.wav",
        },
        "duration": 7.5,
        "source": "upload",
    }
    calls = []

    class FakeModalUploadClient:
        def submit_video(self, video_path, *, uploader_hf_username, style_key, scene_hint):
            calls.append((video_path, uploader_hf_username, style_key, scene_hint))
            return scene

    class FakeMediaClient:
        base_url = ""

        def media_url(self, path):
            return f"/gradio_api/file=/tmp/{Path(path).name}" if path else None

    monkeypatch.setattr(viewer, "_video_duration_s", lambda _path: 7.5)
    monkeypatch.setattr(viewer, "_modal_upload_client", lambda: FakeModalUploadClient())

    header, stage, feed, audio, shelf, state, visibility = viewer._submit_modal_upload(
        "clip.mp4",
        "deadpan",
        "show the ending",
        viewer._pack_engine_ui_state([], None, None, None),
        SimpleNamespace(name="Alice Example", username="alice"),
        FakeMediaClient(),
    )

    assert calls == [("clip.mp4", "alice", "deadpan", "show the ending")]
    assert "A Modal Scene" in header
    assert "clip.mp4" in stage
    assert "sc-ico-upload" in stage
    assert "real voice" in feed
    assert "voice.wav" in audio
    assert shelf == [("/tmp/frame.jpg", f"{viewer.UPLOAD_SHELF_PREFIX}A Modal Scene")]
    assert state["upload_scene"]["scene_id"] == "modal-1"
    assert state["current_id"] == "modal-1"
    assert state["playing_id"] == "modal-1"
    assert visibility["value"] == "public"


def test_bucket_scene_client_reads_manifest_and_caches_media(tmp_path, monkeypatch):
    class FakeBucketFs:
        def __init__(self, files):
            self.files = files
            self.seen = []

        def cat(self, path):
            self.seen.append(path)
            return self.files[path]

    media = {
        "frame_url": "media/9f1c7e4a/frame.jpg",
        "card_url": "media/9f1c7e4a/card.webp",
        "audio_url": "media/9f1c7e4a/voice.wav",
        "clip_url": "media/9f1c7e4a/clip.mp4",
    }
    scene = {**GOLDEN_SCENE, "media": media}
    root = "hf://buckets/build-small-hackathon/small-cuts-scenes/relay"
    fake_fs = FakeBucketFs(
        {
            f"{root}/manifest.json": json.dumps({"scenes": [scene]}).encode(),
            f"{root}/media/9f1c7e4a/frame.jpg": b"frame",
            f"{root}/media/9f1c7e4a/card.webp": b"card",
            f"{root}/media/9f1c7e4a/voice.wav": b"voice",
            f"{root}/media/9f1c7e4a/clip.mp4": b"clip",
        }
    )
    monkeypatch.setattr(viewer.gr, "set_static_paths", lambda _paths: None)

    client = viewer.BucketSceneClient(
        "build-small-hackathon/small-cuts-scenes",
        prefix="relay",
        fs=fake_fs,
        cache_dir=tmp_path,
    )

    (hydrated,) = client.list_scenes()
    frame_url = hydrated["media"]["frame_url"]
    assert frame_url.startswith("/gradio_api/file=")
    assert Path(unquote(frame_url.removeprefix("/gradio_api/file="))).read_bytes() == b"frame"
    assert (tmp_path / "media/9f1c7e4a/voice.wav").read_bytes() == b"voice"
    assert f"{root}/manifest.json" in fake_fs.seen


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
    assert payload["source_icon"] is None


def test_stage_html_escapes_caption_and_has_no_rec_chip():
    out = viewer.render_stage_html("http://x/f.jpg", "a <script> walks in", live=True)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    # the stage no longer carries a REC chip — live/finished state lives in the header
    assert "REC" not in out


def test_stage_html_shows_source_badges():
    glasses = viewer.render_stage_html(
        "http://x/f.jpg", "caption", live=False, source_icon="glasses"
    )
    upload = viewer.render_stage_html("http://x/f.jpg", "caption", live=False, source_icon="upload")

    assert "sc-source-badge" in glasses
    assert "sc-ico-glasses" in glasses
    assert "Glasses capture" in glasses
    assert "sc-source-badge" in upload
    assert "sc-ico-upload" in upload
    assert "Space upload" in upload

    assert "sc-source-badge" not in viewer.render_stage_html(
        "http://x/f.jpg", "caption", live=False, source_icon=None
    )


def test_shelf_items_marks_source_tiles():
    class FakeMediaClient:
        def media_url(self, path):
            return f"/media/{path}" if path else None

    glasses_scene = {
        **GOLDEN_SCENE,
        "source": "glasses",
        "title": "A Glasses Scene",
        "media": {"frame_url": "frame.jpg"},
    }
    upload_scene = {
        **GOLDEN_SCENE,
        "source": "upload",
        "title": "An Upload Scene",
        "media": {"frame_url": "upload.jpg"},
    }

    items = viewer.shelf_items([glasses_scene, upload_scene], FakeMediaClient())

    assert items[0] == ("/media/frame.jpg", f"{viewer.GLASSES_SHELF_PREFIX}A Glasses Scene")
    assert items[1] == ("/media/upload.jpg", f"{viewer.UPLOAD_SHELF_PREFIX}An Upload Scene")


def test_shelf_items_unwraps_gradio_file_routes_for_gallery(tmp_path):
    cached = tmp_path / "relay" / "media" / "frame.jpg"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"fake")

    class FakeMediaClient:
        def media_url(self, path):
            return f"{viewer.GRADIO_FILE_ROUTE}{cached}" if path else None

    (item,) = viewer.shelf_items(
        [{**GOLDEN_SCENE, "media": {"frame_url": "frame.jpg"}}],
        FakeMediaClient(),
    )

    assert item == (str(cached), GOLDEN_SCENE["title"])


def test_playback_js_uses_trusted_dom_click_for_audio():
    # Browser audio user activation is tied to the real click call stack. Routing play through
    # gr.Button.click(js=...) can run too late and trigger NotAllowedError on the Space.
    assert "closest('.sc-play-btn')" in viewer.PLAYBACK_SYNC_JS
    assert "pointerdown" in viewer.PLAYBACK_SYNC_JS
    assert "audio.play()" in viewer.PLAYBACK_SYNC_JS
    assert "audio play blocked" in viewer.PLAYBACK_SYNC_JS


def test_header_live_reads_happening_now_else_title():
    live = viewer.render_header_html("The Bicycle Is Mustard Yellow", "noir", live=True)
    assert "Happening now" in live
    assert "The Bicycle Is Mustard Yellow" not in live  # live capture hides the per-cut title
    finished = viewer.render_header_html("The Bicycle Is Mustard Yellow", "noir", live=False)
    assert "The Bicycle Is Mustard Yellow" in finished
    assert "Happening now" not in finished


def test_feed_renders_newest_first_for_column_reverse():
    entries = [
        viewer.feed_entry({"style_key": "noir", "narration": "first", "created_at": "x"}),
        viewer.feed_entry({"style_key": "trailer", "narration": "second", "created_at": "x"}),
    ]
    html = viewer.render_feed_html(entries)
    # column-reverse pins the scroll to the bottom, so newest must lead the DOM
    assert html.index("second") < html.index("first")
    # one unnamed signature voice — every line is authored by "Narrator", never a style name
    assert html.count("Narrator") == 2


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
    assert "Happening now" in header  # fresh scene = live capture
    assert f"{ENGINE_URL}/media/9f1c7e4a/frame.jpg" in stage
    assert "mustard yellow" in feed
    # audio is now the hidden master-clock <audio> element carrying the served voice URL
    assert "<audio" in audio and 'id="sc-voice"' in audio
    assert f"{ENGINE_URL}/media/9f1c7e4a/voice.wav" in audio
    assert shelf == [(f"{ENGINE_URL}/media/9f1c7e4a/frame.jpg", "The Bicycle Is Mustard Yellow")]
    assert scenes == [GOLDEN_SCENE]
    assert current == GOLDEN_SCENE["scene_id"]
    assert playing == GOLDEN_SCENE["scene_id"]


def test_poll_engine_finished_scene_shows_title():
    def handler(request):
        return httpx.Response(200, json={"scenes": [GOLDEN_SCENE]})

    now = CREATED_AT + timedelta(minutes=10)
    header, _stage, *_rest = viewer.poll_engine(
        fake_client(handler), [], pinned_id=None, playing_id=None, now=now
    )
    assert "Happening now" not in header  # stale = a finished cut
    assert "The Bicycle Is Mustard Yellow" in header


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


def test_poll_engine_announces_new_live_without_interrupting_current_scene():
    older = {
        **GOLDEN_SCENE,
        "scene_id": "older",
        "title": "The Door Waits Politely",
        "created_at": (CREATED_AT - timedelta(seconds=20)).isoformat(),
        "media": {
            **GOLDEN_SCENE["media"],
            "frame_url": "/media/older/frame.jpg",
            "audio_url": "/media/older/voice.wav",
        },
    }
    newer = {
        **GOLDEN_SCENE,
        "scene_id": "newer",
        "title": "The Street Becomes Evidence",
        "created_at": CREATED_AT.isoformat(),
        "media": {
            **GOLDEN_SCENE["media"],
            "frame_url": "/media/newer/frame.jpg",
            "audio_url": "/media/newer/voice.wav",
        },
    }

    def handler(request):
        return httpx.Response(200, json={"scenes": [older, newer]})

    header, stage, _feed, audio, _shelf, _scenes, current, playing, _vis = viewer.poll_engine(
        fake_client(handler),
        [older],
        pinned_id=None,
        playing_id=older["scene_id"],
        current_id=older["scene_id"],
        now=CREATED_AT + timedelta(seconds=5),
    )

    assert "New cut available" in header
    assert "Tap to watch" in header
    assert f"{ENGINE_URL}/media/older/frame.jpg" in stage
    assert f"{ENGINE_URL}/media/newer/frame.jpg" not in stage
    assert audio == gr.skip()
    assert current == older["scene_id"]
    assert playing == older["scene_id"]


def test_step_index_wraps_library_edges():
    scenes = [{"scene_id": "a"}, {"scene_id": "b"}, {"scene_id": "c"}]

    assert viewer._stepped_scene(scenes, "a", -1)["scene_id"] == "c"
    assert viewer._stepped_scene(scenes, "c", 1)["scene_id"] == "a"
    assert viewer._stepped_scene(scenes, None, 1)["scene_id"] == "a"
    assert viewer._stepped_scene(scenes, None, -1)["scene_id"] == "b"


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
    monkeypatch.delenv("SMALL_CUTS_TTS_BACKEND", raising=False)
    header, stage, feed, shelf, audio, scenes, pinned = viewer._go_live_handler(
        make_image(), None, "noir", "", []
    )
    assert audio is not None  # voice-over is generated by default
    assert len(scenes) == 1
    scene = scenes[0]
    assert scene["style_key"] == "noir"
    assert scene["narration"]
    assert scene["title"] == viewer.derive_title(scene["narration"])
    assert scene["frame_src"].startswith("data:image/jpeg;base64,")
    assert scene["frame_src"] in stage
    assert scene["title"] in header  # an upload is a finished cut -> title, not "Happening now"
    assert "Narrator" in feed
    assert shelf == [(scene["card_thumb"], scene["title"])]
    assert pinned is None


def test_local_scene_thumbnail_uses_stage_frame_not_title_card():
    frame = make_image(color=(10, 220, 120))
    card = make_image(width=1280, height=720, color=(220, 10, 10))

    scene = viewer.make_local_scene(frame, card, "The title card stays elsewhere.", "deadpan")

    color = scene["card_thumb"].resize((1, 1)).getpixel((0, 0))
    assert color[1] > color[0]
    assert color[1] > color[2]


def test_go_live_handler_without_moment_still_narrates(monkeypatch):
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)
    *_page, scenes, _pinned = viewer._go_live_handler(None, None, "deadpan", "", [])
    assert len(scenes) == 1
    assert "scene" in scenes[0]["narration"].lower()  # the empty-stage easter egg


def test_go_live_handler_video_uses_key_frame(monkeypatch):
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)
    key_frame = make_image(color=(10, 220, 120))
    captured = {}

    monkeypatch.setattr(viewer, "sample_frames", lambda _path: [make_image(), key_frame])
    monkeypatch.setattr(viewer, "pick_key_frame", lambda frames: frames[-1])

    def fake_narrate_core(frame, style_key, scene_hint, empty_caption):
        captured["frame"] = frame
        return make_image(width=1280, height=720), "The frame has been chosen deliberately."

    monkeypatch.setattr(viewer, "_narrate_core", fake_narrate_core)

    viewer._go_live_handler(None, "clip.mp4", "deadpan", "", [])

    assert captured["frame"] is key_frame


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


def test_scene_actions_are_scoped_to_current_scene():
    liked, reported = {"a"}, {"b"}

    assert viewer._scene_action_classes("a", liked, reported) == (
        ["sc-icbtn", "sc-ico-like-filled", "sc-like-btn"],
        ["sc-icbtn", "sc-ico-flag", "sc-report-btn"],
    )
    assert viewer._scene_action_classes("b", liked, reported) == (
        ["sc-icbtn", "sc-ico-like", "sc-like-btn"],
        ["sc-icbtn", "sc-ico-flag-filled", "sc-report-btn"],
    )


def test_scene_action_toggles_target_only_current_scene():
    liked, reported = set(), set()

    liked, like_update = viewer._toggle_scene_like("a", liked, reported)
    assert liked == {"a"}
    assert "sc-ico-like-filled" in like_update["elem_classes"]

    reported, report_update = viewer._toggle_scene_report("b", liked, reported)
    assert reported == {"b"}
    assert "sc-ico-flag-filled" in report_update["elem_classes"]
    assert "sc-ico-like-filled" not in report_update["elem_classes"]


# -- review-hardening regressions (cross-family Codex+GLM review, 2026-06-14) ----------


def test_go_live_handler_survives_tts_failure(monkeypatch):
    """A TTS hiccup on the Space must degrade to no voice, not crash the stage."""
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)

    def boom(*_args, **_kwargs):
        raise RuntimeError("kokoro fork poisoned")

    monkeypatch.setattr(viewer, "speak", boom)
    _header, stage, _feed, _shelf, audio, scenes, _pinned = viewer._go_live_handler(
        make_image(), None, "noir", "", []
    )
    # TTS failed -> an empty <audio> host (no src = no voice), but the stage still renders
    assert "<audio" in audio and "src=" not in audio
    assert scenes[0]["audio_src"] is None
    assert len(scenes) == 1  # ...but the scene still staged
    assert "sc-stage-shell" in stage


def test_go_live_handler_writes_voice_file(monkeypatch):
    """The generated voice-over is written to a served WAV so shelf replay isn't silent."""
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)
    monkeypatch.delenv("SMALL_CUTS_TTS_BACKEND", raising=False)
    _header, _stage, _feed, _shelf, audio, scenes, _pinned = viewer._go_live_handler(
        make_image(), None, "noir", "", []
    )
    audio_src = scenes[0]["audio_src"]
    assert audio_src is not None and audio_src.endswith(".wav")
    assert Path(audio_src).exists()  # written to the served generated-audio dir
    # the page's audio slot carries that file as the master-clock <audio> element
    assert "<audio" in audio and "gradio_api/file=" in audio


def test_subtitle_chunks_are_short_and_robust():
    """Phrase-sized lines, capped at max_words, resilient to whitespace and long words."""
    chunks = viewer._subtitle_chunks(
        "A long sentence that should be split into several small caption pieces here."
    )
    assert chunks
    assert max(len(c.split()) for c in chunks) <= 5
    assert isinstance(viewer._subtitle_chunks("   "), list)  # no crash on whitespace
    long_word = "x" * 80
    assert viewer._subtitle_chunks(long_word) == [long_word]


def test_stage_html_whitespace_caption_renders_no_subtitle():
    assert "sc-subtitle" not in viewer.render_stage_html("http://x/f.jpg", "   ", live=True)


def test_stage_html_embeds_duration_and_coerces_strings():
    numeric = viewer.render_stage_html("http://x/f.jpg", "Hello there.", live=True, duration=24.5)
    assert 'data-duration="24.5"' in numeric
    # a stringy duration from a loose payload must coerce, not TypeError
    stringy = viewer.render_stage_html("http://x/f.jpg", "Hi.", live=True, duration="12.0")
    assert 'data-duration="12.0"' in stringy


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
