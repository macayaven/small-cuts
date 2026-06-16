from __future__ import annotations

import base64
import io
from pathlib import Path
from urllib.parse import unquote

import numpy as np
import soundfile as sf
from PIL import Image

from small_cuts.hf_relay import GRADIO_FILE_ROUTE
from small_cuts.upload_library import LocalUploadLibrary


def _jpeg_data_uri(color: tuple[int, int, int] = (100, 120, 140)) -> str:
    image = Image.new("RGB", (18, 24), color)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _path_from_file_url(value: str) -> Path:
    assert value.startswith(GRADIO_FILE_ROUTE)
    return Path(unquote(value[len(GRADIO_FILE_ROUTE) :]))


def test_save_scene_materializes_media_and_reloads_from_disk(tmp_path):
    wav_path = tmp_path / "voice.wav"
    sf.write(wav_path, np.zeros(1200, dtype=np.float32), 24_000)
    clip_path = tmp_path / "clip.mp4"
    clip_path.write_bytes(b"fake-video")
    scene = {
        "scene_id": "local-test-scene",
        "title": "Persisted Cut",
        "narration": "The narrator remembers this one.",
        "style_key": "deadpan",
        "created_at": "2026-06-16T10:00:00+00:00",
        "frame_src": _jpeg_data_uri(),
        "audio_src": f"{GRADIO_FILE_ROUTE}{wav_path}",
        "card_thumb": Image.new("RGB", (20, 20), (20, 30, 40)),
    }

    library = LocalUploadLibrary(tmp_path / "library")
    saved = library.save_scene(scene, source_video_path=clip_path)
    reloaded = LocalUploadLibrary(tmp_path / "library").list_scenes()

    assert saved["scene_id"] == "local-test-scene"
    assert len(reloaded) == 1
    persisted = reloaded[0]
    assert persisted["source"] == "upload"
    assert persisted["source_icon"] == "upload"
    assert "owner" not in persisted
    assert "card_thumb" not in persisted
    assert "frame_src" not in persisted
    assert "audio_src" not in persisted
    assert _path_from_file_url(persisted["media"]["frame_url"]).is_file()
    assert _path_from_file_url(persisted["media"]["card_url"]).is_file()
    assert _path_from_file_url(persisted["media"]["audio_url"]).is_file()
    assert _path_from_file_url(persisted["media"]["clip_url"]).is_file()


def test_list_scenes_is_oldest_to_newest_and_limited(tmp_path):
    library = LocalUploadLibrary(tmp_path / "library")
    for index in range(3):
        library.save_scene(
            {
                "scene_id": f"scene-{index}",
                "title": f"Cut {index}",
                "narration": "A short remembered scene.",
                "style_key": "deadpan",
                "created_at": f"2026-06-16T10:0{index}:00+00:00",
                "frame_src": _jpeg_data_uri((index, index, index)),
            },
        )

    scenes = library.list_scenes(limit=2)

    assert [scene["scene_id"] for scene in scenes] == ["scene-1", "scene-2"]
