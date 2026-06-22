"""Mid Cuts (Small Cuts v2) — Modal ``/v2/narrate`` endpoint.

Greenfield. Whole-clip narration: Qwen3-Omni (video in → narration TEXT + deadpan SPEECH in
``--language``) → a contract-valid NarratedScene + media → the private ``macayaven/small-cuts-data``
bucket with a WRITE-scoped token. The scene-building / publish / backend-interface logic lives in
the importable ``small_cuts.narrate_v2`` (unit-tested); this file is the thin Modal wrapper.

NEVER touches the ``small-cuts-postcut`` app (v1), which the hackathon submission
``build-small-hackathon/small-cuts`` shares — keep it untouched.

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

BUCKET_ID = "macayaven/small-cuts-data"
RELAY_PREFIX = "relay"
OMNI_MODEL = "Qwen/Qwen3-Omni-30B-A3B-Instruct"
ALIGNER_MODEL = "Qwen/Qwen3-ForcedAligner-0.6B"
OMNI_GPU = "H200"
ALIGNER_GPU = "L4"  # 0.6B aligner: a cheap modern bf16 GPU is plenty.
SPEAKER = "Aiden"
MAX_UPLOAD_BYTES = 30 * 1024 * 1024
MAX_UPLOAD_SECONDS = 30.0
BEARER_ENV = "SMALL_CUTS_MODAL_API_TOKEN"
WRITE_TOKEN_ENV = "SMALL_CUTS_RELAY_WRITE_TOKEN"
# Push-not-poll: the Space's relay hook URL + the Bearer it shares with this producer. Both live in
# the `mid-cuts` Modal secret; when absent the publish still succeeds and the poll endpoint is used.
HOOK_URL_ENV = "SMALL_CUTS_RELAY_HOOK_URL"
HOOK_TOKEN_ENV = "SMALL_CUTS_RELAY_HOOK_TOKEN"

# Narration prompts/carriers + the title cleaner live in the importable, unit-tested
# small_cuts.narrate_v2 (imported inside the GPU methods, where /root/src is on sys.path).

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

# Separate image for the ForcedAligner: qwen-asr hard-pins transformers==4.57.6, which conflicts
# with Omni's git-main, so the carrier-cut step must run in its own container (DESIGN/Phase-0).
# Don't pin huggingface-hub here (>=1.19 sends the resolver into anyio backtracking).
aligner_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "qwen-asr",
        "torch>=2.4",
        "accelerate>=1.0",
        "numpy>=1.26",
        # small_cuts/__init__ registers the HEIF opener at import time, so importing
        # small_cuts.narrate_v2 (for carrier_cut_index) needs pillow + pillow-heif here too.
        "pillow>=10.0",
        "pillow-heif>=0.18",
    )
    .env({"HF_HOME": "/cache/hf"})
    .add_local_dir("src", remote_path="/root/src")  # for small_cuts.narrate_v2.carrier_cut_index
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

    def _omni_generate(
        self, frames: list, system_prompt: str, user_prompt: str, *, return_audio: bool
    ) -> tuple[str, Any]:
        """Run ONE Omni pass over the decoded frames. Returns (text, audio); ``audio`` is None when
        ``return_audio`` is False (the text-only title pass — no Talker, no spoken JSON braces)."""
        from qwen_omni_utils import process_mm_info

        use_audio = False  # the frame list carries no audio
        conversation = [
            {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
            {
                "role": "user",
                "content": [
                    {"type": "video", "video": frames},
                    {"type": "text", "text": user_prompt},
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
        generate_kwargs: dict[str, Any] = {
            "use_audio_in_video": use_audio,
            "return_audio": return_audio,
        }
        if return_audio:
            generate_kwargs["speaker"] = SPEAKER
        generated = self.model.generate(**inputs, **generate_kwargs)
        if return_audio:
            text_ids, audio = generated
        else:
            text_ids = generated[0] if isinstance(generated, tuple | list) else generated
            audio = None
        decoded = self.processor.batch_decode(
            text_ids[:, inputs["input_ids"].shape[1] :],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0].strip()
        return decoded, audio

    def _narrate(
        self, frames: list, language: str, *, prime: bool, context: str = ""
    ) -> tuple[str, Any, int]:
        """Narration pass → (text, wav, sample_rate). ``prime`` prepends the warm-up carrier (later
        trimmed by the aligner) to defeat the autoregressive cold-start accent ramp. ``context`` is
        the optional free-text *manner* steer (how the moment is told)."""
        from small_cuts.narrate_v2 import build_narration_prompts

        system_prompt, user_prompt = build_narration_prompts(language, prime=prime, context=context)
        narration, audio = self._omni_generate(
            frames, system_prompt, user_prompt, return_audio=True
        )
        wav = audio.reshape(-1).detach().cpu().numpy()
        return narration, wav, 24_000

    def _title(self, frames: list, language: str) -> str:
        """Title pass → a short evocative title (raw model text, cleaned by clean_model_title). A
        SEPARATE text-only pass: the spoken narration pass can't emit JSON (the Talker would speak
        the braces), so the model title comes from its own return_audio=False generation."""
        from small_cuts.narrate_v2 import build_title_prompts

        system_prompt, user_prompt = build_title_prompts(language)
        title, _ = self._omni_generate(frames, system_prompt, user_prompt, return_audio=False)
        return title

    @modal.method()
    def process(
        self,
        video_bytes: bytes,
        filename: str,
        style_key: str = "deadpan",
        language: str = "English",
        context: str = "",
    ) -> dict[str, Any]:
        sys.path.insert(0, "/root/src")
        import json
        import shutil
        from uuid import uuid4

        import jsonschema
        import soundfile as sf
        from huggingface_hub import HfApi

        from small_cuts.narrate_v2 import (
            PRIME_CARRIER,
            build_narrated_scene,
            clean_model_title,
            has_carrier,
            notify_relay_hook,
            publish_scene,
        )

        work = Path(tempfile.mkdtemp(prefix="midcuts-"))
        input_path = work / Path(filename).name
        input_path.write_bytes(video_bytes)

        frames = _sample_video_frames(input_path)
        if not frames:
            raise RuntimeError("no decodable video frames")

        # 1) narration pass — carrier-primed when a warm-up carrier exists for the language. The
        # optional free-text `context` steers HOW the moment is told (manner, not facts).
        use_prime = has_carrier(language)
        narration, wav, sample_rate = self._narrate(
            frames, language, prime=use_prime, context=context
        )

        # 2) warm-up cut (L4 aligner, separate container) — align the carrier+narration speech, find
        # where the carrier ends, and drop it; the remaining audio is already past the cold-start
        # ramp. Best-effort: a degenerate cut (empty real text) falls back to the untrimmed take.
        # Trade-off: this blocking .remote() keeps the H200 alive while the L4 cold-starts; accepted
        # because the two models can't share an image (qwen-asr pins an older transformers).
        # timed_captions come from the SAME alignment (rebased past the carrier) — soft CC track,
        # only on the trimmed take; None when there's no carrier or the cut fell back to untrimmed.
        timed_captions = None
        if use_prime:
            cut = Aligner().cut_carrier.remote(
                wav=wav,
                sample_rate=sample_rate,
                full_text=narration,
                carrier=PRIME_CARRIER[language],
                language=language,
            )
            if cut.get("real_text"):
                narration, wav, sample_rate = (
                    cut["real_text"],
                    cut["trimmed_wav"],
                    cut["sample_rate"],
                )
                timed_captions = cut.get("timed_captions") or None
            else:
                print(
                    "midcuts: carrier cut produced empty narration; publishing untrimmed",
                    file=sys.stderr,
                    flush=True,
                )

        # 3) title pass — a SEPARATE text-only Omni pass (the spoken pass can't emit JSON). Falls
        # back to derive_title(narration) only when the model title is malformed/empty (contract).
        title = clean_model_title(self._title(frames, language), fallback=_derive_title(narration))

        scene_id = str(uuid4())
        media_dir = work / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        frame_path = media_dir / "frame.jpg"
        clip_path = media_dir / "clip.mp4"
        voice_path = media_dir / "voice.wav"
        frames[0].convert("RGB").save(frame_path, "JPEG", quality=90)
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
            title=title,
            style_key=style_key,
            media=media,
            captured_at=now,
            created_at=now,
            scene_id=scene_id,
            duration=duration,
            keyframe_time=0.0,
            timed_captions=timed_captions,
            engine={
                "narrator_model": OMNI_MODEL,
                "narrator_backend": "transformers",
                "tts_model": OMNI_MODEL,
            },
            # v2 sends the persona key in style_key, so persona aliases it (display provenance).
            persona=style_key,
            language=language,
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
        # Push-not-poll: tell the read-only Space a new cut landed so open browsers refresh once.
        # Best-effort — the scene is already durably in the bucket; a hook outage never fails this.
        notify_relay_hook(
            os.environ.get(HOOK_URL_ENV),
            os.environ.get(HOOK_TOKEN_ENV),
            scene_id=scene["scene_id"],
            seq=scene["seq"],
        )
        return {"status": "complete", "scene": scene}


@app.cls(
    image=aligner_image,
    gpu=ALIGNER_GPU,
    timeout=900,
    volumes={"/cache": hf_cache},
    min_containers=0,
    buffer_containers=0,
    scaledown_window=60,
    max_containers=2,
)
class Aligner:
    """ForcedAligner in its own image (transformers==4.57.6) — used only to trim the warm-up
    carrier off the front of the narration audio. No bucket secret: it never publishes."""

    @modal.enter()
    def load(self) -> None:
        import torch
        from qwen_asr import Qwen3ForcedAligner

        self.aligner = Qwen3ForcedAligner.from_pretrained(
            ALIGNER_MODEL, dtype=torch.bfloat16, device_map="cuda:0"
        )

    @modal.method()
    def cut_carrier(
        self,
        *,
        wav: Any,
        sample_rate: int,
        full_text: str,
        carrier: str,
        language: str,
    ) -> dict[str, Any]:
        """Align the carrier+narration speech to ``full_text``, find where the carrier ends, and
        return the real narration text + the wav with the warm-up sliced off the front. An empty
        ``real_text`` (degenerate alignment) signals the caller to publish the untrimmed take."""
        sys.path.insert(0, "/root/src")
        import numpy as np

        from small_cuts.narrate_v2 import plan_carrier_cut

        data = np.asarray(wav, dtype="float32")
        results = self.aligner.align(audio=(data, sample_rate), text=full_text, language=language)
        words = [
            {"word": w.text, "t_start": float(w.start_time), "t_end": float(w.end_time)}
            for w in results[0]
        ]
        # Pure planner (unit-tested): drop the carrier, derive real_text, and build rebased caption
        # cues. A punctuation-only tail yields real_text="" + no cues → publish the untrimmed take.
        t_cut, real_text, timed_captions = plan_carrier_cut(words, carrier)
        trimmed = data[int(round(t_cut * sample_rate)) :]
        return {
            "real_text": real_text,
            "trimmed_wav": trimmed,
            "sample_rate": sample_rate,
            "t_cut": t_cut,
            "timed_captions": timed_captions,
        }


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
    context: Annotated[str, Form()] = "",
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
    call = await Narrator().process.spawn.aio(payload, safe_filename, style_key, language, context)
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

    from small_cuts.narrate_v2 import (
        MockNarrationBackend,
        build_narrated_scene,
        build_narration_prompts,
        build_title_prompts,
        clean_model_title,
    )

    # New-pipeline wiring smoke (CPU): prompts resolve + title cleaner works before any GPU spend.
    primed_system, primed_user = build_narration_prompts("Spanish", prime=True)
    assert "«" in primed_system  # carrier instruction embedded
    # Manner-steer wiring (Phase 5 step 1): empty context is a byte-identical no-op; a non-empty
    # context is injected BEFORE the carrier instruction so the carrier still closes the prompt.
    assert build_narration_prompts("Spanish", prime=True, context="") == (
        primed_system,
        primed_user,
    )
    carrier_tail = primed_system[primed_system.index("«") :]  # carrier instruction (must stay last)
    steered, _ = build_narration_prompts("Spanish", prime=True, context="en tono nostálgico")
    assert "en tono nostálgico" in steered and steered.endswith(carrier_tail)
    assert all(build_title_prompts(lang)[0] for lang in ("English", "Spanish", "French"))
    assert clean_model_title('"Probe"', fallback="x") == "Probe"

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


@app.function(image=aligner_image, timeout=300)
def smoke_aligner() -> dict[str, Any]:
    """CPU-only: prove the aligner image imports qwen-asr AND can import the shared cut helper from
    the small_cuts package (which registers the HEIF opener at import) — catches a missing
    pillow-heif/pillow in the L4 image before any GPU spend. No model load."""
    sys.path.insert(0, "/root/src")
    import transformers
    from qwen_asr import Qwen3ForcedAligner  # noqa: F401

    from small_cuts.narrate_v2 import carrier_cut_index, has_speech_content

    assert carrier_cut_index([], "carrier") == (0.0, -1)
    assert has_speech_content("hola") and not has_speech_content(".")
    return {"ok": True, "transformers": transformers.__version__}


@app.local_entrypoint()
def smoke_main() -> None:
    print(smoke.remote())
    print(smoke_aligner.remote())


@app.local_entrypoint()
def e2e(clip: str = "rayuela", language: str = "English", context: str = "") -> None:
    """GPU H200: narrate a real seed clip end-to-end and write the scene to small-cuts-data.

    Pass ``--context`` to judge the free-text manner steer by ear (e.g. ``--context "wistful"``).
    """
    video_bytes = Path(f"src/small_cuts/seed_media/{clip}.mp4").read_bytes()
    out = Narrator().process.remote(video_bytes, f"{clip}.mp4", "deadpan", language, context)
    print(f"status={out['status']} scene_id={out['scene']['scene_id']}")
    print(f"narration: {out['scene']['narration']}")
    print(f"media: {out['scene']['media']}")
