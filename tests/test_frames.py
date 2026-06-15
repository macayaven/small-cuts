from pathlib import Path

import av
import pytest
from PIL import Image

from small_cuts.frames import pick_frame, pick_key_frame, sample_frames

FIXTURES = Path("~/small-cuts-fixtures/videos").expanduser()


def _write_clip(path: Path, n_frames: int, fps: int = 30) -> Path:
    container = av.open(str(path), mode="w")
    stream = container.add_stream("mpeg4", rate=fps)
    stream.width, stream.height = 64, 48
    stream.pix_fmt = "yuv420p"
    for i in range(n_frames):
        img = Image.new("RGB", (64, 48), (i % 255, 100, 50))
        for packet in stream.encode(av.VideoFrame.from_image(img)):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()
    return path


def test_sample_frames_count(tmp_path):
    clip = _write_clip(tmp_path / "clip.mp4", n_frames=90)  # 3s @ 30fps
    frames = sample_frames(clip, every_n_seconds=1.0)
    assert len(frames) == 3  # frames 0, 30, 60


def test_sample_frames_short_clip_never_empty(tmp_path):
    clip = _write_clip(tmp_path / "short.mp4", n_frames=10)
    assert len(sample_frames(clip, every_n_seconds=3.0)) >= 1


def test_sample_frames_no_side_effect_files(tmp_path):
    clip = _write_clip(tmp_path / "clip.mp4", n_frames=30)
    sample_frames(clip)
    assert [p.name for p in tmp_path.iterdir()] == ["clip.mp4"]


def test_sample_frames_returns_rgb_pil(tmp_path):
    clip = _write_clip(tmp_path / "clip.mp4", n_frames=30)
    for frame in sample_frames(clip, every_n_seconds=0.5):
        assert isinstance(frame, Image.Image)
        assert frame.mode == "RGB"


def test_sample_frames_max_frames_stops_early(tmp_path):
    clip = _write_clip(tmp_path / "clip.mp4", n_frames=120)
    frames = sample_frames(clip, every_n_seconds=0.5, max_frames=2)
    assert len(frames) == 2


def test_pick_frame_returns_middle():
    frames = [Image.new("RGB", (8, 8), c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
    assert pick_frame(frames).getpixel((0, 0)) == (0, 255, 0)


def test_pick_frame_empty_raises():
    with pytest.raises(ValueError):
        pick_frame([])


def test_pick_key_frame_prefers_detailed_well_exposed_frame():
    flat_start = Image.new("RGB", (32, 32), (8, 8, 8))
    flat_end = Image.new("RGB", (32, 32), (245, 245, 245))
    detailed = Image.new("RGB", (32, 32), (36, 120, 76))
    pixels = detailed.load()
    for y in range(32):
        for x in range(32):
            if (x + y) % 2:
                pixels[x, y] = (215, 220, 180)

    assert pick_key_frame([flat_start, detailed, flat_end]) is detailed


def test_pick_key_frame_empty_raises():
    with pytest.raises(ValueError):
        pick_key_frame([])


def test_eval_wrapper_still_saves_jpegs(tmp_path):
    from small_cuts.eval import _sample_video_frames

    clip = _write_clip(tmp_path / "clip.mp4", n_frames=90)
    out_paths = _sample_video_frames(clip, every_n_seconds=1.0)
    assert len(out_paths) == 3
    assert all(p.exists() and p.suffix == ".jpg" for p in out_paths)


def test_video_handler_narrates_with_mock_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("SMALL_CUTS_BACKEND", "mock")
    from small_cuts.ui import _narrate_video_handler

    clip = _write_clip(tmp_path / "clip.mp4", n_frames=90)
    card, text = _narrate_video_handler(str(clip), "deadpan", "")
    assert "Deadpan" in text  # mock narration includes the style label
    assert card.size == (1280, 720)  # title card rides along since M2 (#12)


@pytest.mark.skipif(not FIXTURES.exists(), reason="real glasses fixtures not staged")
@pytest.mark.parametrize("clip", sorted(FIXTURES.glob("IMG_*")) if FIXTURES.exists() else [])
def test_real_glasses_clip_decodes_upright(clip):
    frames = sample_frames(clip, every_n_seconds=3.0, max_frames=2)
    assert frames, f"no frames decoded from {clip.name}"
    for frame in frames:
        assert frame.height > frame.width  # glasses footage is native portrait
