"""The seeded 'hero' VIDEO library: content shape, bundled media, and the viewer boots with it."""

import os

import gradio as gr

from small_cuts import demo_seed, viewer


def test_seed_has_five_curated_video_cuts():
    assert len(demo_seed.SEED) == 5
    for clip, poster, title, narration, visibility in demo_seed.SEED:
        assert clip.endswith(".mp4")
        assert poster.endswith(".jpg")
        assert title and narration
        assert visibility in ("private", "shared", "public")
        # the bundled media actually ships with the package
        assert os.path.exists(demo_seed.clip_path(clip))
        assert os.path.exists(os.path.join(demo_seed.SEED_DIR, poster))


def test_seed_posters_load():
    img = demo_seed.load_poster(demo_seed.SEED[0][1])
    assert img.mode == "RGB" and img.size[0] > 0


def test_seed_scenes_play_video_and_read_standby():
    scenes = viewer._seed_scenes()
    assert len(scenes) == 5
    for scene in scenes:
        assert scene["style_key"] == "deadpan"
        assert scene["clip_src"].startswith("/gradio_api/file=") and scene["clip_src"].endswith(
            ".mp4"
        )
        assert scene["frame_src"].startswith("data:image/jpeg;base64,")  # the poster still
        assert scene["title"] and scene["narration"]
        # dated into the past → finished cut, reads STANDBY (the library is not live)
        assert viewer.is_fresh(scene["created_at"]) is False


def test_stage_renders_video_when_clip_present():
    html = viewer.render_stage_html(
        "data:image/jpeg;base64,xxx", "a caption", live=False, clip_src="/gradio_api/file=/x/c.mp4"
    )
    assert "<video" in html and "/gradio_api/file=/x/c.mp4" in html
    assert "autoplay muted loop playsinline" in html
    # no clip → falls back to a still image
    img_html = viewer.render_stage_html("http://x/f.jpg", "c", live=True)
    assert "<img" in img_html and "<video" not in img_html


def test_upload_mode_boots_with_the_seed(monkeypatch):
    monkeypatch.delenv(viewer.ENGINE_URL_ENV, raising=False)
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)
    assert isinstance(viewer.build_viewer_app(), gr.Blocks)
