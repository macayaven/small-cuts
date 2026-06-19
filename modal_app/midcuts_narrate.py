"""Mid Cuts (Small Cuts v2) — Modal ``/v2/narrate`` endpoint.

Greenfield. Whole-clip narration: Qwen3-Omni (video in → narration TEXT + deadpan SPEECH in
``--language``) → a contract-valid NarratedScene + media → the private ``macayaven/mid-cuts``
bucket with a WRITE-scoped token. The scene-building / publish / backend-interface logic lives in
the importable ``small_cuts.narrate_v2`` (unit-tested); this file is the thin Modal wrapper.

NEVER touches the live ``macayaven/small-cuts`` Space or the old ``small-cuts-postcut`` app.

Run (after Carlos's go — spends Modal GPU credits):
    modal run modal_app/midcuts_narrate.py::smoke      # CPU: image imports + writer wiring, no GPU
    modal run modal_app/midcuts_narrate.py::e2e   # GPU H200: narrate a seed clip → bucket
Deploy the HTTP endpoint (needs a Bearer added to the `mid-cuts` secret) — later:
    modal deploy modal_app/midcuts_narrate.py
"""

from __future__ import annotations

import hmac
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import fastapi
import modal
from fastapi import File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

BUCKET_ID = "macayaven/mid-cuts"
RELAY_PREFIX = "relay"
OMNI_MODEL = "Qwen/Qwen3-Omni-30B-A3B-Instruct"
OMNI_GPU = "H200"
SPEAKER = "Aiden"
MAX_UPLOAD_BYTES = 30 * 1024 * 1024
MAX_UPLOAD_SECONDS = 30.0
BEARER_ENV = "SMALL_CUTS_MODAL_API_TOKEN"
WRITE_TOKEN_ENV = "SMALL_CUTS_RELAY_WRITE_TOKEN"

DEADPAN_SYS = (
    "You are a film narrator. Watch the clip and write ONE short, flat, factual sentence "
    "describing the moment. Declarative only. No exclamations, no emphasis, no emotion words, "
    "no asterisks, brackets, parentheses, or stage directions. Neutral, monotone, deadpan."
)
USER_PROMPT = "Narrate this moment."

hf_cache = modal.Volume.from_name("midcuts-hf-cache", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "ffmpeg")
    .pip_install(
        "torch>=2.4",
        "torchvision>=0.19",
        "accelerate>=1.0",
        "soundfile>=0.12",
        "av>=12.0",
        "pillow>=10.0",
        "pillow-heif>=0.18",  # small_cuts/__init__ registers the HEIF opener at import time
        "jsonschema[format]>=4.0",  # [format] enables the uuid/date-time/uri-reference checkers
        "huggingface-hub>=1.19",
        "qwen-omni-utils",
        "fastapi[standard]",
        "git+https://github.com/huggingface/transformers.git",  # Qwen3-Omni needs git main
    )
    .env({"HF_HOME": "/cache/hf"})
    .add_local_dir("src", remote_path="/root/src")
    .add_local_dir("docs/contracts", remote_path="/root/docs/contracts")
    .add_local_dir("src/small_cuts/seed_media", remote_path="/root/seed_media")
)

app = modal.App("midcuts-narrate")
# Bearer-gated; the browsable schema routes add only surface, so disable them.
web_app = fastapi.FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def _require_bearer(authorization: str | None) -> None:
    """Fail-closed Bearer check (DESIGN §7 #5): timing-safe compare, 401 on a missing secret."""
    expected = os.environ.get(BEARER_ENV, "")
    provided = (authorization or "").removeprefix("Bearer ")
    if not expected or not hmac.compare_digest(provided, expected):
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


def _sample_video_frames(path: Path, target_fps: float = 2.0, max_frames: int = 48):
    """Decode to PIL frames with PyAV (a frame list makes qwen-omni-utils skip its file reader)."""
    import av

    frames = []
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        step = max(1, round(float(stream.average_rate or 30) / target_fps))
        for index, frame in enumerate(container.decode(stream)):
            if index % step == 0:
                frames.append(frame.to_image())
                if len(frames) >= max_frames:
                    break
    return frames


def _derive_title(narration: str) -> str:
    first = narration.strip().split(".")[0].strip() or narration.strip()
    return first[:80]


@app.cls(
    image=image,
    gpu=OMNI_GPU,
    timeout=900,
    volumes={"/cache": hf_cache},
    secrets=[modal.Secret.from_name("mid-cuts")],
    min_containers=0,
    buffer_containers=0,
    scaledown_window=60,
    max_containers=2,
)
class Narrator:
    @modal.enter()
    def load(self) -> None:
        import torch
        from transformers import Qwen3OmniMoeForConditionalGeneration, Qwen3OmniMoeProcessor

        self.model = Qwen3OmniMoeForConditionalGeneration.from_pretrained(
            OMNI_MODEL, dtype=torch.bfloat16, device_map="cuda:0", attn_implementation="sdpa"
        )
        self.processor = Qwen3OmniMoeProcessor.from_pretrained(OMNI_MODEL)

    def _narrate(self, clip_path: Path, language: str) -> tuple[str, Any, int]:
        from qwen_omni_utils import process_mm_info

        frames = _sample_video_frames(clip_path)
        use_audio = False  # frame list carries no audio
        conversation = [
            {
                "role": "system",
                "content": [
                    {"type": "text", "text": f"{DEADPAN_SYS} Write the narration in {language}."}
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "video", "video": frames},
                    {"type": "text", "text": USER_PROMPT},
                ],
            },
        ]
        text = self.processor.apply_chat_template(
            conversation, add_generation_prompt=True, tokenize=False
        )
        audios, images, videos = process_mm_info(conversation, use_audio_in_video=use_audio)
        inputs = self.processor(
            text=text,
            audio=audios,
            images=images,
            videos=videos,
            return_tensors="pt",
            padding=True,
            use_audio_in_video=use_audio,
        )
        inputs = inputs.to(self.model.device).to(self.model.dtype)
        text_ids, audio = self.model.generate(
            **inputs, speaker=SPEAKER, use_audio_in_video=use_audio, return_audio=True
        )
        narration = self.processor.batch_decode(
            text_ids[:, inputs["input_ids"].shape[1] :],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0].strip()
        wav = audio.reshape(-1).detach().cpu().numpy()
        return narration, wav, 24_000

    @modal.method()
    def process(
        self,
        video_bytes: bytes,
        filename: str,
        style_key: str = "deadpan",
        language: str = "English",
    ) -> dict[str, Any]:
        sys.path.insert(0, "/root/src")
        import json
        import shutil

        import jsonschema
        import soundfile as sf
        from huggingface_hub import HfApi

        from small_cuts.narrate_v2 import build_narrated_scene, publish_scene

        work = Path(tempfile.mkdtemp(prefix="midcuts-"))
        input_path = work / Path(filename).name
        input_path.write_bytes(video_bytes)

        narration, wav, sample_rate = self._narrate(input_path, language)

        from uuid import uuid4

        scene_id = str(uuid4())
        media_dir = work / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        frame_path = media_dir / "frame.jpg"
        clip_path = media_dir / "clip.mp4"
        voice_path = media_dir / "voice.wav"
        first_frames = _sample_video_frames(input_path, max_frames=1)
        if not first_frames:
            raise RuntimeError("no decodable video frames")
        first_frames[0].convert("RGB").save(frame_path, "JPEG", quality=90)
        if input_path.suffix.lower() in {".mp4", ".mov", ".m4v"}:
            shutil.copyfile(input_path, clip_path)
        else:
            import subprocess

            subprocess.run(
                ["ffmpeg", "-y", "-i", str(input_path), "-c:v", "libx264", str(clip_path)],
                check=True,
                capture_output=True,
            )
        sf.write(voice_path, wav, sample_rate)

        media = {
            "frame_url": f"uploads/{scene_id}/media/frame.jpg",
            "clip_url": f"uploads/{scene_id}/media/clip.mp4",
            "audio_url": f"uploads/{scene_id}/media/voice.wav",
        }
        now = datetime.now(timezone.utc).isoformat()
        # duration = playback (narration-audio) length = the single-clock player's clock, NOT the
        # source-clip length. keyframe_time = the poster frame's offset; the poster is the first
        # decoded frame today (0.0) — representative-frame selection is a fast-follow.
        duration = float(len(wav) / sample_rate) if sample_rate else None
        scene = build_narrated_scene(
            narration=narration,
            title=_derive_title(narration),
            style_key=style_key,
            media=media,
            captured_at=now,
            created_at=now,
            scene_id=scene_id,
            duration=duration,
            keyframe_time=0.0,
            engine={
                "narrator_model": OMNI_MODEL,
                "narrator_backend": "transformers",
                "tts_model": OMNI_MODEL,
            },
        )

        # Runtime conformance guard (DESIGN §6): never publish a scene that fails the contract.
        schema = json.loads((Path("/root/docs/contracts/narrated-scene.schema.json")).read_text())
        jsonschema.validate(
            scene, schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER
        )

        write_token = os.environ.get(WRITE_TOKEN_ENV) or None
        if write_token is None:
            raise RuntimeError(
                f"{WRITE_TOKEN_ENV} missing from the Modal secret; refusing anonymous write"
            )
        api = HfApi(token=write_token)

        def uploader(local: Path, remote: str) -> None:
            api.batch_bucket_files(BUCKET_ID, add=[(str(local), remote)])

        publish_scene(
            uploader,
            prefix=RELAY_PREFIX,
            scene=scene,
            media_files={"frame.jpg": frame_path, "clip.mp4": clip_path, "voice.wav": voice_path},
            work_dir=work,
        )
        return {"status": "complete", "scene": scene}


@app.function(
    image=image,
    timeout=60,
    min_containers=0,
    buffer_containers=0,
    scaledown_window=60,
    secrets=[modal.Secret.from_name("mid-cuts")],
)
@modal.concurrent(max_inputs=20, target_inputs=10)
@modal.asgi_app()
def api():
    return web_app


@web_app.post("/v2/narrate")
async def narrate_endpoint(
    video: Annotated[UploadFile, File()],
    style_key: Annotated[str, Form()] = "deadpan",
    language: Annotated[str, Form()] = "English",
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    _require_bearer(authorization)
    payload = await video.read()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="video is too large")
    safe_filename = Path(video.filename or "upload.mp4").name
    with tempfile.TemporaryDirectory(prefix="midcuts-accept-") as tmp:
        probe = Path(tmp) / safe_filename
        probe.write_bytes(payload)
        try:
            duration_s = _video_duration_s(probe)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="could not decode video") from exc
    if duration_s > MAX_UPLOAD_SECONDS + 0.25:
        raise HTTPException(
            status_code=422, detail=f"video is too long; upload up to {MAX_UPLOAD_SECONDS:.0f}s"
        )
    call = await Narrator().process.spawn.aio(payload, safe_filename, style_key, language)
    return {"job_id": call.object_id}


@web_app.get("/v2/narrate/{job_id}")
def poll_narrate(job_id: str, authorization: str | None = Header(default=None)):
    _require_bearer(authorization)
    call = modal.FunctionCall.from_id(job_id)
    try:
        return call.get(timeout=0)
    except TimeoutError:
        return JSONResponse({"status": "running"}, status_code=202)


@app.function(image=image, timeout=300)
def smoke() -> dict[str, Any]:
    """CPU-only: prove the image imports and the writer wiring works end-to-end with the mock
    backend (no GPU, no model). Catches import/contract errors before spending on H200."""
    sys.path.insert(0, "/root/src")
    import json

    import jsonschema

    from small_cuts.narrate_v2 import MockNarrationBackend, build_narrated_scene

    result = MockNarrationBackend().narrate(
        Path("/root/seed_media/rayuela.mp4"), language="Spanish"
    )
    now = datetime.now(timezone.utc).isoformat()
    scene = build_narrated_scene(
        narration=result.text,
        title=_derive_title(result.text),
        style_key="deadpan",
        media={"frame_url": "uploads/x/media/frame.jpg"},
        captured_at=now,
        created_at=now,
        engine={
            "narrator_backend": result.narrator_backend,
            "narrator_model": result.narrator_model,
        },
    )
    schema = json.loads(Path("/root/docs/contracts/narrated-scene.schema.json").read_text())
    jsonschema.validate(
        scene, schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER
    )
    return {"ok": True, "scene_id": scene["scene_id"], "narration": result.text}


@app.local_entrypoint()
def smoke_main() -> None:
    print(smoke.remote())


@app.local_entrypoint()
def e2e(clip: str = "rayuela", language: str = "English") -> None:
    """GPU H200: narrate a real seed clip end-to-end and write the scene to the mid-cuts bucket."""
    video_bytes = Path(f"src/small_cuts/seed_media/{clip}.mp4").read_bytes()
    out = Narrator().process.remote(video_bytes, f"{clip}.mp4", "deadpan", language)
    print(f"status={out['status']} scene_id={out['scene']['scene_id']}")
    print(f"narration: {out['scene']['narration']}")
    print(f"media: {out['scene']['media']}")
