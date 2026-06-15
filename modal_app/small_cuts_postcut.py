from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import fastapi
import modal
from fastapi import File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

BUCKET_ID = os.environ.get("SMALL_CUTS_RELAY_BUCKET", "macayaven/small-cuts-scenes-dev")
RELAY_PREFIX = "relay"
MAX_UPLOAD_BYTES = 80 * 1024 * 1024
MAX_UPLOAD_SECONDS = 60.0
MAX_SAMPLE_FRAMES = 40

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "fastapi[standard]",
        "huggingface-hub>=1.19",
        "pillow>=10.0",
        "pillow-heif>=0.18",
        "av>=12.0",
        "soundfile>=0.12",
        "transformers>=4.49",
        "torch>=2.4",
        "torchvision>=0.19",
        "accelerate>=1.0",
        "kokoro>=0.9",
    )
    .add_local_dir("src", remote_path="/root/src")
    .add_local_dir("docs/contracts", remote_path="/root/docs/contracts")
)

app = modal.App("small-cuts-postcut")
web_app = fastapi.FastAPI()


def _require_bearer(authorization: str | None) -> None:
    expected = os.environ["SMALL_CUTS_MODAL_API_TOKEN"]
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="unauthorized")


def _video_duration_s(path: Path) -> float:
    import av

    with av.open(str(path)) as container:
        if container.duration is not None:
            return float(container.duration / 1_000_000)
        stream = container.streams.video[0]
        if stream.duration is not None and stream.time_base is not None:
            return float(stream.duration * stream.time_base)
    raise ValueError("could not determine video duration")


def _sample_interval_s(duration_s: float) -> float:
    return max(0.5, duration_s / MAX_SAMPLE_FRAMES)


@app.function(
    image=image,
    timeout=60,
    min_containers=0,
    buffer_containers=0,
    scaledown_window=60,
    secrets=[modal.Secret.from_name("small-cuts-postcut")],
)
@modal.concurrent(max_inputs=20, target_inputs=10)
@modal.asgi_app()
def api():
    return web_app


@web_app.post("/v1/cuts")
async def accept_cut(
    video: Annotated[UploadFile, File()],
    style_key: Annotated[str, Form()] = "deadpan",
    scene_hint: Annotated[str, Form()] = "",
    uploader_hf_username: Annotated[str, Form()] = "unknown",
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    _require_bearer(authorization)
    payload = await video.read()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="video is too large")
    safe_filename = Path(video.filename or "upload.mp4").name
    with tempfile.TemporaryDirectory(prefix="small-cuts-accept-") as tmp:
        probe_path = Path(tmp) / safe_filename
        probe_path.write_bytes(payload)
        try:
            duration_s = _video_duration_s(probe_path)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="could not decode video") from exc
    if duration_s > MAX_UPLOAD_SECONDS + 0.25:
        raise HTTPException(
            status_code=422,
            detail=f"video is too long; upload up to {MAX_UPLOAD_SECONDS:.0f} seconds",
        )
    call = await process_cut.spawn.aio(
        payload,
        safe_filename,
        style_key,
        scene_hint,
        uploader_hf_username,
        duration_s,
    )
    return {"job_id": call.object_id}


@web_app.get("/v1/cuts/{job_id}")
def poll_cut(job_id: str, authorization: str | None = Header(default=None)):
    _require_bearer(authorization)
    call = modal.FunctionCall.from_id(job_id)
    try:
        return call.get(timeout=0)
    except TimeoutError:
        return JSONResponse({"status": "running"}, status_code=202)


@app.function(
    image=image,
    gpu=["H100", "A100-80GB", "L40S"],
    timeout=900,
    min_containers=0,
    buffer_containers=0,
    max_containers=4,
    scaledown_window=60,
    secrets=[modal.Secret.from_name("small-cuts-postcut")],
)
def process_cut(
    video_bytes: bytes,
    filename: str,
    style_key: str,
    scene_hint: str,
    uploader_hf_username: str,
    upload_duration_s: float,
) -> dict[str, Any]:
    sys.path.insert(0, "/root/src")
    os.environ.setdefault("SMALL_CUTS_BACKEND", "transformers")
    os.environ.setdefault("SMALL_CUTS_TTS_BACKEND", "kokoro")

    import shutil

    import soundfile as sf
    from huggingface_hub import HfApi

    from small_cuts.engine.library import _write_clip_mp4
    from small_cuts.frames import pick_key_frame, sample_frames
    from small_cuts.narrator import narrate
    from small_cuts.title_card import render_title_card
    from small_cuts.tts import speak

    scene_id = f"modal-{uuid.uuid4().hex[:12]}"
    work = Path(tempfile.mkdtemp(prefix="small-cuts-modal-"))
    input_path = work / Path(filename).name
    input_path.write_bytes(video_bytes)

    frames = sample_frames(
        input_path,
        every_n_seconds=_sample_interval_s(upload_duration_s),
        max_frames=MAX_SAMPLE_FRAMES,
    )
    if not frames:
        raise RuntimeError("could not decode video frames")
    key_frame = pick_key_frame(frames)
    narration = narrate(key_frame, style_key=style_key, scene_hint=scene_hint)
    speech = speak(narration.text)

    upload_prefix = f"uploads/{scene_id}"
    scene_dir = work / upload_prefix
    media_dir = scene_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    frame_path = media_dir / "frame.jpg"
    card_path = media_dir / "card.webp"
    clip_path = media_dir / "clip.mp4"
    voice_path = media_dir / "voice.wav"
    key_frame.convert("RGB").save(frame_path, "JPEG", quality=90)
    render_title_card(narration.title or narration.text, style_key=style_key).save(
        card_path, "WEBP"
    )
    # Use the wearer's natural footage as the clip — not a sampled slideshow. H.264 mp4/mov/m4v
    # play in-browser as-is; fall back to the frame slideshow only for other containers (e.g. webm).
    if input_path.suffix.lower() in {".mp4", ".mov", ".m4v"}:
        shutil.copyfile(input_path, clip_path)
    else:
        _write_clip_mp4(clip_path, frames, fps=8, blend_steps=0)
    sf.write(voice_path, speech.audio, speech.sample_rate)

    scene = {
        "scene_id": scene_id,
        "title": narration.title,
        "narration": narration.text,
        "style_key": style_key,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "visibility": "public",
        "uploader_hf_username": uploader_hf_username,
        "source": "upload",
        "media": {
            "frame_url": f"{upload_prefix}/media/frame.jpg",
            "card_url": f"{upload_prefix}/media/card.webp",
            "clip_url": f"{upload_prefix}/media/clip.mp4",
            "audio_url": f"{upload_prefix}/media/voice.wav",
        },
        "duration": len(speech.audio) / speech.sample_rate if speech.sample_rate else None,
        "model": narration.model_id,
        "tts_model": speech.model_id,
    }
    (scene_dir / "scene.json").write_text(json.dumps(scene, indent=2) + "\n")
    HfApi().sync_bucket(
        source=str(scene_dir),
        dest=f"hf://buckets/{BUCKET_ID}/{RELAY_PREFIX}/{upload_prefix}",
    )
    return {"status": "complete", "scene": scene}
