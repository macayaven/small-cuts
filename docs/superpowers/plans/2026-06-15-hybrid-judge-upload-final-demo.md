# Hybrid Judge Upload And Final Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move judge uploads to Modal while preserving the non-negotiable private glasses-to-ear live narration demo and publishing glasses cuts from the already-generated local artifacts.

**Architecture:** Keep four flows separate while validating them in order. The submitted org Space (`build-small-hackathon/small-cuts-live`) remains a CPU Basic Gradio viewer/uploader with HF OAuth on uploads. Modal hosts only the judge/browser upload service that runs Qwen3-VL-8B + Kokoro, writes finished upload artifacts to the HF bucket relay, and returns scene metadata to the Space. The glasses/iOS path remains private and real-time to the wearer's ear on the Mac Studio; `Action!` starts the take and `Cut!` finalizes it, returns local ear narration, and can auto-publish that already-finished local scene to the relay bucket without reaching Modal. Glasses-origin scenes carry a source marker so the Space can show a small glasses icon in the top-left of the clip/library tile. ZeroGPU is only a fallback if Modal fails quickly.

**Tech Stack:** Gradio, Hugging Face Spaces CPU Basic, HF OAuth, Modal Web Functions + GPU Functions, HF bucket relay, PyAV/H.264 MP4 generation, Qwen3-VL-8B, Kokoro TTS, SwiftUI iOS app, FastAPI engine, Ray-Ban Meta glasses.

---

## Current Timebox

Plan timestamp: 2026-06-15 12:43 UTC / 14:43 CEST.

Submission deadline: 2026-06-15 23:59 UTC / 2026-06-16 01:59 CEST.

Time remaining at plan update: about 11 h 16 m.

## Decisions Locked By This Plan

- Do a short physical glasses smoke before public library population. This confirms the non-negotiable glasses -> iPhone -> Mac engine -> in-ear narration path before spending time polishing public artifacts.
- Do not expand the iOS real-time WebSocket payload to 60 seconds just for the Space. That would risk upload latency and the ear-first experience.
- Implement the 60-second video upload as a hosted judge verification path. The Space accepts the
  completed clip, requires HF login for upload, sends the clip to Modal with a server-side bearer
  secret, and replays the Modal-generated scene with synced captions.
- Prove the hosted inference path first with a private Modal POC endpoint. Do not deploy upload
  controls to the submitted org Space until Modal cold/warm timing, artifact writing, and playback
  behavior are measured.
- The submitted Space should be hybrid:
  - relay viewer/library from `SMALL_CUTS_RELAY_BUCKET`;
  - upload drawer enabled by `SMALL_CUTS_ENABLE_UPLOAD_SANDBOX=1` and
    `SMALL_CUTS_MODAL_API_URL`.
- The upload drawer must use real Modal-hosted narration/TTS, not mock output. Keep
  `build-small-hackathon/small-cuts-live` on CPU Basic unless Modal is ruled out and the fallback
  ZeroGPU path is deliberately chosen.
- Glasses-origin cuts do not use Modal. `Cut!` remains the only wearer-side completion action:
  after the local engine has produced clip, narration, title, and speech, a demo/admin publisher can
  sync that completed scene to the relay bucket automatically. The Space renders those scenes with a
  small glasses icon in the top-left of the stage/library tile.
- Public library clips should be longer and generated honestly from real glasses clips with the same model prompt/title/TTS path, not hand-written captions.

## File Responsibilities

- `app.py`: keep the submitted Space viewer/uploader lightweight on CPU Basic; do not load local model/TTS backends when Modal upload is configured.
- `modal_app/small_cuts_postcut.py`: Modal FastAPI app + GPU worker for post-cut video inference, TTS, artifact writing, and job polling.
- `src/small_cuts/modal_upload.py`: Space-side Modal client with bearer auth, file upload, polling, and result normalization.
- `src/small_cuts/viewer.py`: hybrid relay + upload UI, HF login requirement for uploads, 60-second upload validation, uploaded-video stage replay, glasses-source badge rendering, upload pinning so relay polling does not overwrite the judge's uploaded result.
- `src/small_cuts/engine/library.py`: reusable MP4 writer options for upload/library clip generation.
- `src/small_cuts/frames.py`: optional duration helper and bounded frame sampling tests.
- `tests/test_modal_upload.py`: Modal client auth, polling, timeout, and scene normalization.
- `tests/test_app_entrypoint.py`: Space backend selection stays viewer-only when Modal upload is configured.
- `tests/test_viewer.py`: upload drawer visibility, HF login gate, 60-second cap, uploaded clip replay, relay polling not interrupting an uploaded result.
- `tests/test_engine_library.py`: MP4 writer FPS/blend behavior for longer clips.
- `scripts/measure_modal_upload.py`: optional timing harness if browser-only timing is too manual.
- `ios/SmallCuts/SmallCuts/Capture/CaptureCoordinator.swift`: restore explicit wearer captions/status for the real-time glasses path.
- `ios/SmallCuts/SmallCuts/UI/ContentView.swift`: only if the caption pane needs copy/layout adjustment.
- `ios/SmallCuts/SmallCutsTests/CaptureCoordinatorTakeTests.swift`: caption state tests for Cut -> waiting -> SceneAudio.
- `scripts/publish_hf_relay.py` or a new `scripts/build_demo_relay_library.py`: publish only selected, controlled longer clips to the relay bucket and preserve `source="glasses"` metadata.
- `docs/demo-readiness.md`: keep the active state updated after each gate.

## Task 0: Modal Post-Cut POC

**Files/Services:**
- Create: `modal_app/small_cuts_postcut.py`
- Modal app: `small-cuts-postcut`
- Modal secret: `small-cuts-postcut` with `HF_TOKEN` and `SMALL_CUTS_MODAL_API_TOKEN`
- Modal GPU policy: performance-first for the hackathon grant, `["H100", "A100-80GB", "L40S"]`
  fallbacks, `min_containers=1`, `buffer_containers=1`, `max_containers=4`, no same-container
  GPU concurrency for model/TTS.
- HF bucket: `build-small-hackathon/small-cuts-scenes`, prefix `relay`
- Evidence: update `docs/demo-readiness.md`

- [ ] **Step 1: Verify Modal auth without printing secrets**

Run:

```bash
modal profile current
modal secret list | rg '^small-cuts-postcut\\b' || true
```

Expected: Modal CLI is authenticated and the secret either already exists or is clearly absent. If it
is absent, create it from already-loaded environment variables only:

```bash
modal secret create small-cuts-postcut \
  HF_TOKEN="$HF_TOKEN" \
  SMALL_CUTS_MODAL_API_TOKEN="$SMALL_CUTS_MODAL_API_TOKEN"
```

Expected: the command succeeds and does not echo either token value.

- [ ] **Step 2: Create the Modal app shell**

Create `modal_app/small_cuts_postcut.py`:

```python
from __future__ import annotations

import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fastapi
import modal
from fastapi import File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

BUCKET_ID = "build-small-hackathon/small-cuts-scenes"
RELAY_PREFIX = "relay"
MAX_UPLOAD_BYTES = 80 * 1024 * 1024

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
)

app = modal.App("small-cuts-postcut")
web_app = fastapi.FastAPI()


def _require_bearer(authorization: str | None) -> None:
    expected = os.environ["SMALL_CUTS_MODAL_API_TOKEN"]
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="unauthorized")
```

Expected: `python -m py_compile modal_app/small_cuts_postcut.py` passes locally after `modal` is
installed.

- [ ] **Step 3: Add job accept and poll endpoints**

Add this below `_require_bearer()`:

```python
@app.function(
    image=image,
    timeout=60,
    min_containers=1,
    buffer_containers=1,
    scaledown_window=1200,
    secrets=[modal.Secret.from_name("small-cuts-postcut")],
)
@modal.concurrent(max_inputs=20, target_inputs=10)
@modal.asgi_app()
def api():
    return web_app


@web_app.post("/v1/cuts")
async def accept_cut(
    video: UploadFile = File(...),
    style_key: str = Form("deadpan"),
    scene_hint: str = Form(""),
    uploader_hf_username: str = Form("unknown"),
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    _require_bearer(authorization)
    payload = await video.read()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="video is too large")
    call = process_cut.spawn(
        payload,
        video.filename or "upload.mp4",
        style_key,
        scene_hint,
        uploader_hf_username,
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
```

Expected: the HTTP endpoint returns immediately with a `job_id`, so the Space does not depend on a
single long HTTP request.

- [ ] **Step 4: Add the GPU worker**

Add this worker to the same file:

```python
@app.function(
    image=image,
    gpu=["H100", "A100-80GB", "L40S"],
    timeout=900,
    min_containers=1,
    buffer_containers=1,
    max_containers=4,
    scaledown_window=1200,
    secrets=[modal.Secret.from_name("small-cuts-postcut")],
)
def process_cut(
    video_bytes: bytes,
    filename: str,
    style_key: str,
    scene_hint: str,
    uploader_hf_username: str,
) -> dict[str, Any]:
    sys.path.insert(0, "/root/src")
    os.environ.setdefault("SMALL_CUTS_BACKEND", "transformers")
    os.environ.setdefault("SMALL_CUTS_TTS_BACKEND", "kokoro")

    import soundfile as sf
    from huggingface_hub import HfApi

    from small_cuts.engine.library import _write_clip_mp4
    from small_cuts.frames import pick_key_frame, sample_frames
    from small_cuts.narrator import narrate
    from small_cuts.title_card import render_title_card
    from small_cuts.tts import speak

    scene_id = f"modal-{uuid.uuid4().hex[:12]}"
    work = Path(tempfile.mkdtemp(prefix="small-cuts-modal-"))
    input_path = work / filename
    input_path.write_bytes(video_bytes)

    frames = sample_frames(input_path, every_n_seconds=0.5, max_frames=40)
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
    render_title_card(narration.title or narration.text, style_key=style_key).save(card_path, "WEBP")
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
    (scene_dir / "scene.json").write_text(__import__("json").dumps(scene, indent=2) + "\n")
    HfApi().sync_bucket(source=str(work), dest=f"hf://buckets/{BUCKET_ID}/{RELAY_PREFIX}")
    return {"status": "complete", "scene": scene}
```

Expected: the worker writes per-upload artifacts under `relay/uploads/<scene_id>/` and returns a
scene payload that matches `format_stage()` expectations after the Space hydrates bucket-relative
media paths. It must not overwrite the relay `manifest.json`; the public library manifest remains
owned by the glasses/local publisher. The API endpoint can handle concurrent polling/submission, but
GPU work scales by containers instead of same-container threading because the Qwen/Kokoro pipeline is
not assumed thread-safe.

- [ ] **Step 5: Serve locally through Modal and smoke health**

Run:

```bash
modal serve modal_app/small_cuts_postcut.py
```

In another shell, submit a short MP4 using the printed Modal URL:

```bash
curl -sS -H "Authorization: Bearer $SMALL_CUTS_MODAL_API_TOKEN" \
  -F "video=@/absolute/path/to/short-test.mp4" \
  -F "style_key=deadpan" \
  -F "uploader_hf_username=local-smoke" \
  "$MODAL_URL/v1/cuts"
```

Expected: JSON contains `job_id`.

- [ ] **Step 6: Poll the Modal result**

Run:

```bash
curl -sS -H "Authorization: Bearer $SMALL_CUTS_MODAL_API_TOKEN" \
  "$MODAL_URL/v1/cuts/$JOB_ID"
```

Expected: returns `202` while running and then `{"status":"complete","scene":{...}}` with real
generated title/narration/audio artifacts in the bucket.

- [ ] **Step 7: Deploy Modal only after local serve passes**

Run:

```bash
modal deploy modal_app/small_cuts_postcut.py
```

Expected: Modal prints the deployed HTTPS endpoint. Save only the URL and timing evidence in
`docs/demo-readiness.md`; do not write token values anywhere.

- [ ] **Step 8: Measure cold and warm upload timings**

Record at least three runs in `docs/demo-readiness.md`:

```text
modal_cold_start_s:
modal_warm_upload_1_s:
modal_warm_upload_2_s:
video_duration_s:
gpu_policy: H100 -> A100-80GB -> L40S
warm_pool: min_containers=1, buffer_containers=1, max_containers=4
model_backend:
tts_backend:
result_quality:
```

Promotion threshold:

- Cold run can be slow but must complete without crash.
- Warm 5-60 second uploads target under 60 seconds; acceptable fallback is under 120 seconds if the
  page clearly shows progress and the demo video covers the live experience.
- Narration must be real Qwen output and audio must be real Kokoro output.

- [ ] **Step 9: Commit**

```bash
git add modal_app/small_cuts_postcut.py docs/demo-readiness.md
git commit -m "Add Modal post-cut POC"
```

## Task 1: Space Runtime And Modal Client

**Files:**
- Modify: `app.py`
- Create: `src/small_cuts/modal_upload.py`
- Test: `tests/test_app_entrypoint.py`
- Test: `tests/test_modal_upload.py`

- [ ] **Step 1: Write entrypoint test for Modal upload mode staying lightweight**

Add this to `tests/test_app_entrypoint.py`:

```python
def test_space_relay_with_modal_upload_does_not_force_local_backends(monkeypatch):
    monkeypatch.setenv("SPACE_ID", "build-small-hackathon/small-cuts-live")
    monkeypatch.delenv("SMALL_CUTS_ENGINE_URL", raising=False)
    monkeypatch.setenv("SMALL_CUTS_RELAY_BUCKET", "build-small-hackathon/small-cuts-scenes")
    monkeypatch.setenv("SMALL_CUTS_ENABLE_UPLOAD_SANDBOX", "1")
    monkeypatch.setenv("SMALL_CUTS_MODAL_API_URL", "https://example.modal.run")
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)
    monkeypatch.delenv("SMALL_CUTS_TTS_BACKEND", raising=False)
    monkeypatch.setitem(sys.modules, "spaces", None)

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    spec = importlib.util.spec_from_file_location("_small_cuts_test_app_modal", app_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert os.environ.get("SMALL_CUTS_BACKEND") is None
    assert os.environ.get("SMALL_CUTS_TTS_BACKEND") is None
```

- [ ] **Step 2: Implement runtime selection**

Change the top-level mode logic in `app.py` to this shape:

```python
ENGINE_MODE = bool(os.environ.get("SMALL_CUTS_ENGINE_URL", "").strip())

from small_cuts.hf_relay import RELAY_BUCKET_ENV  # noqa: E402

RELAY_MODE = bool(os.environ.get(RELAY_BUCKET_ENV, "").strip())
MODAL_UPLOAD_MODE = bool(os.environ.get("SMALL_CUTS_MODAL_API_URL", "").strip())
VIEWER_ONLY_MODE = ENGINE_MODE or RELAY_MODE or MODAL_UPLOAD_MODE
NEEDS_LOCAL_INFERENCE = not VIEWER_ONLY_MODE

if ON_SPACE and NEEDS_LOCAL_INFERENCE:
    os.environ.setdefault("SMALL_CUTS_BACKEND", "transformers")
    os.environ.setdefault("SMALL_CUTS_TTS_BACKEND", "kokoro")
```

Keep the eager narrator load under `if NEEDS_LOCAL_INFERENCE:`. The submitted Space should stay CPU
Basic when `SMALL_CUTS_MODAL_API_URL` is set.

- [ ] **Step 3: Write Modal client tests**

Create `tests/test_modal_upload.py`:

```python
from __future__ import annotations

import httpx
import pytest

from small_cuts.modal_upload import ModalUploadClient, ModalUploadError


def test_modal_client_submits_and_polls_result(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            assert request.headers["authorization"] == "Bearer secret"
            return httpx.Response(200, json={"job_id": "job-1"})
        if request.url.path.endswith("/job-1") and len(calls) == 2:
            return httpx.Response(202, json={"status": "running"})
        return httpx.Response(200, json={"status": "complete", "scene": {"scene_id": "s1"}})

    client = ModalUploadClient(
        "https://modal.example",
        "secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        poll_interval_s=0,
    )

    assert client.submit_video(video, uploader_hf_username="alice")["scene_id"] == "s1"
    assert calls == [
        ("POST", "/v1/cuts"),
        ("GET", "/v1/cuts/job-1"),
        ("GET", "/v1/cuts/job-1"),
    ]


def test_modal_client_rejects_missing_scene(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"job_id": "job-1"})
        return httpx.Response(200, json={"status": "complete"})

    client = ModalUploadClient(
        "https://modal.example",
        "secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        poll_interval_s=0,
    )

    with pytest.raises(ModalUploadError, match="scene"):
        client.submit_video(video, uploader_hf_username="alice")
```

- [ ] **Step 4: Create the Space-side Modal client**

Create `src/small_cuts/modal_upload.py`:

```python
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


class ModalUploadError(RuntimeError):
    """Raised when hosted post-cut inference fails."""


@dataclass
class ModalUploadClient:
    base_url: str
    token: str
    http_client: httpx.Client | None = None
    poll_interval_s: float = 1.0
    timeout_s: float = 180.0

    def submit_video(
        self,
        video_path: str | Path,
        *,
        uploader_hf_username: str,
        style_key: str = "deadpan",
        scene_hint: str = "",
    ) -> dict[str, Any]:
        close = self.http_client is None
        client = self.http_client or httpx.Client(timeout=30.0, follow_redirects=True)
        try:
            job_id = self._submit(client, Path(video_path), uploader_hf_username, style_key, scene_hint)
            return self._poll(client, job_id)
        finally:
            if close:
                client.close()

    def _submit(
        self,
        client: httpx.Client,
        video_path: Path,
        uploader_hf_username: str,
        style_key: str,
        scene_hint: str,
    ) -> str:
        with video_path.open("rb") as handle:
            response = client.post(
                f"{self.base_url.rstrip('/')}/v1/cuts",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "style_key": style_key,
                    "scene_hint": scene_hint,
                    "uploader_hf_username": uploader_hf_username,
                },
                files={"video": (video_path.name, handle, "video/mp4")},
            )
        response.raise_for_status()
        job_id = response.json().get("job_id")
        if not isinstance(job_id, str) or not job_id:
            raise ModalUploadError("Modal did not return a job_id")
        return job_id

    def _poll(self, client: httpx.Client, job_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            response = client.get(
                f"{self.base_url.rstrip('/')}/v1/cuts/{job_id}",
                headers={"Authorization": f"Bearer {self.token}"},
            )
            if response.status_code == 202:
                time.sleep(self.poll_interval_s)
                continue
            response.raise_for_status()
            payload = response.json()
            scene = payload.get("scene")
            if not isinstance(scene, dict):
                raise ModalUploadError("Modal completed without a scene payload")
            return scene
        raise ModalUploadError("Modal upload timed out")
```

- [ ] **Step 5: Verify client and entrypoint tests**

Run:

```bash
uv run pytest tests/test_app_entrypoint.py tests/test_modal_upload.py -q
```

Expected: tests pass.

- [ ] **Step 6: Commit**

```bash
git add app.py src/small_cuts/modal_upload.py tests/test_app_entrypoint.py tests/test_modal_upload.py
git commit -m "Route judge uploads to Modal"
```

## Task 2: Space Upload Drawer In Relay Mode

**Files:**
- Modify: `src/small_cuts/viewer.py`
- Test: `tests/test_viewer.py`

- [ ] **Step 1: Write tests for upload availability, login gate, and pinning**

Add pure helper tests that do not require launching the full Gradio app:

```python
def test_upload_sandbox_requires_modal_url(monkeypatch):
    monkeypatch.setenv("SMALL_CUTS_ENABLE_UPLOAD_SANDBOX", "1")
    monkeypatch.delenv("SMALL_CUTS_MODAL_API_URL", raising=False)
    assert viewer.upload_sandbox_enabled() is False
    monkeypatch.setenv("SMALL_CUTS_MODAL_API_URL", "https://example.modal.run")
    assert viewer.upload_sandbox_enabled() is True


def test_upload_requires_hf_profile():
    with pytest.raises(gr.Error, match="Sign in"):
        viewer._require_upload_profile(None)


def test_upload_scene_pins_stage_against_relay_poll():
    upload_scene = {
        "scene_id": "modal-upload-1",
        "title": "A Uploaded Cut",
        "narration": "The hallway waits, already bored.",
        "style_key": "deadpan",
        "created_at": "2026-06-15T12:00:00+00:00",
        "frame_src": "data:image/jpeg;base64,abc",
        "clip_src": "/gradio_api/file=/tmp/upload.mp4",
        "audio_src": "/gradio_api/file=/tmp/upload.wav",
    }
    state = viewer._pack_engine_ui_state(
        scenes=[],
        pinned_id=None,
        current_id=None,
        playing_id=None,
        previous={"upload_scene": upload_scene},
    )
    assert state["upload_scene"]["scene_id"] == "modal-upload-1"
```

- [ ] **Step 2: Add upload helpers**

In `src/small_cuts/viewer.py`, add:

```python
def upload_sandbox_enabled() -> bool:
    flag = os.environ.get("SMALL_CUTS_ENABLE_UPLOAD_SANDBOX", "").strip().lower()
    return flag in {"1", "true", "yes"} and bool(
        os.environ.get("SMALL_CUTS_MODAL_API_URL", "").strip()
    )


def _require_upload_profile(profile: gr.OAuthProfile | None) -> str:
    if profile is None or not getattr(profile, "name", None):
        raise gr.Error("Sign in with Hugging Face to upload a cut.")
    return str(profile.name)
```

Add `gr.LoginButton()` near the existing top controls, visible only when `upload_sandbox_enabled()`
is true. Viewing remains public and anonymous.

- [ ] **Step 3: Keep relay polling from interrupting uploaded results**

Extend `_engine_ui_state()` and `_pack_engine_ui_state()` with an `upload_scene` field:

```python
def _engine_ui_state(value: Any) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    scenes = data.get("scenes")
    upload_scene = data.get("upload_scene")
    return {
        "scenes": scenes if isinstance(scenes, list) else [],
        "pinned_id": data.get("pinned_id"),
        "current_id": data.get("current_id"),
        "playing_id": data.get("playing_id"),
        "upload_scene": upload_scene if isinstance(upload_scene, dict) else None,
    }
```

In `poll_engine()`, if `state["upload_scene"]` is present, update shelf/feed from relay as usual but
return `gr.skip()` for header, stage, and audio so the judge's uploaded result stays on screen until
Back to live clears it.

- [ ] **Step 4: Show the upload drawer when relay mode is active**

In `build_viewer_app()`, replace `if client is None:` checks that gate upload controls with:

```python
upload_enabled = client is None or upload_sandbox_enabled()
```

Use a `gr.State(DEFAULT_STYLE_KEY)` for upload style whenever `upload_enabled` is true. The public UI
should still present one voice/style, not a distracting director menu.

- [ ] **Step 5: Clear uploaded pin on Back to live**

Where the hidden Back to live button currently unpins relay state, also clear `upload_scene`.

- [ ] **Step 6: Verify viewer tests**

Run:

```bash
uv run pytest tests/test_viewer.py -q
```

Expected: all viewer tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/small_cuts/viewer.py tests/test_viewer.py
git commit -m "Show authenticated Modal upload in relay viewer"
```

## Task 3: 20-Second Finished Video Uploads Through Modal

**Files:**
- Modify: `src/small_cuts/viewer.py`
- Modify: `src/small_cuts/engine/library.py`
- Test: `tests/test_viewer.py`
- Test: `tests/test_engine_library.py`

- [ ] **Step 1: Write tests for upload duration and returned scene replay**

Add tests in `tests/test_viewer.py`:

```python
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
```

Add a test in `tests/test_engine_library.py`:

```python
def test_write_clip_mp4_can_disable_blends(tmp_path):
    path = tmp_path / "clip.mp4"
    frames = [Image.new("RGB", (64, 96), (i * 30, 20, 20)) for i in range(4)]
    _write_clip_mp4(path, frames, fps=8, blend_steps=0)
    with av.open(path) as container:
        assert float(container.streams.video[0].average_rate) == pytest.approx(8)
        assert sum(1 for _ in container.decode(video=0)) == 4
```

- [ ] **Step 2: Add upload constants and duration helper**

In `src/small_cuts/viewer.py`, add:

```python
UPLOAD_MAX_SECONDS_ENV = "SMALL_CUTS_UPLOAD_MAX_SECONDS"


def upload_max_seconds() -> float:
    raw = os.environ.get(UPLOAD_MAX_SECONDS_ENV, "60")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 60.0


def _video_duration_s(video_path: str | Path) -> float | None:
    import av

    with av.open(str(video_path)) as container:
        stream = container.streams.video[0]
        if stream.duration is not None and stream.time_base is not None:
            return float(stream.duration * stream.time_base)
        if container.duration is not None:
            return float(container.duration / 1_000_000)
    return None
```

- [ ] **Step 3: Make the MP4 writer configurable for Modal-generated clips**

Change `src/small_cuts/engine/library.py`:

```python
def _write_clip_mp4(
    path: Path,
    frames: list[Image.Image],
    fps: int = CLIP_MP4_FPS,
    blend_steps: int = CLIP_BLEND_STEPS,
) -> None:
    ...
    encode_frames = _smooth_clip_frames(rgb_frames, blend_steps=blend_steps, size=(width, height))
```

Existing callers keep the default blend. Modal and upload paths pass `blend_steps=0` so a sampled
60-second upload does not double its apparent duration.

- [ ] **Step 4: Add the Modal upload handler**

Replace the local `_go_live_handler()` upload path when `upload_sandbox_enabled()` is true:

```python
def _modal_upload_client() -> ModalUploadClient:
    return ModalUploadClient(
        os.environ["SMALL_CUTS_MODAL_API_URL"],
        os.environ["SMALL_CUTS_MODAL_API_TOKEN"],
    )


def _submit_modal_upload(
    video_path: str | None,
    style_key: str,
    scene_hint: str,
    scenes: list[dict[str, Any]],
    profile: gr.OAuthProfile | None,
) -> tuple[Any, ...]:
    if not video_path:
        raise gr.Error("Upload a video clip first.")
    duration = _video_duration_s(video_path)
    if duration is not None and duration > upload_max_seconds() + 0.25:
        raise gr.Error(f"Please upload a clip up to {upload_max_seconds():.0f} seconds.")
    uploader = _require_upload_profile(profile)
    scene = _modal_upload_client().submit_video(
        video_path,
        uploader_hf_username=uploader,
        style_key=style_key,
        scene_hint=scene_hint,
    )
    scenes = [*(scenes or []), scene][-SHELF_LIMIT:]
    payload = format_stage(scene)
    return (
        render_header_html(payload["title"], payload["style_label"], live=False),
        render_stage_html(
            payload["frame_src"],
            payload["caption"],
            live=False,
            clip_src=payload["clip_src"],
            duration=payload["duration"],
        ),
        render_feed_html([feed_entry(s) for s in scenes[-FEED_LIMIT:]]),
        local_shelf_items(scenes),
        _audio_html(payload["audio_src"]) if payload["audio_src"] else gr.skip(),
        scenes,
        scene.get("scene_id"),
        {"upload_scene": scene},
    )
```

Wire this handler to the upload button with `profile: gr.OAuthProfile | None` injected by Gradio.
Keep the old local mock upload handler only for development mode when `SMALL_CUTS_MODAL_API_URL` is
unset.

- [ ] **Step 5: Verify tests**

Run:

```bash
uv run pytest tests/test_viewer.py tests/test_engine_library.py -q
```

Expected: tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/small_cuts/viewer.py src/small_cuts/engine/library.py tests/test_viewer.py tests/test_engine_library.py
git commit -m "Support Modal judge video uploads"
```

## Task 4: Restore Real-Time Wearer Captions

**Files:**
- Modify: `ios/SmallCuts/SmallCuts/Capture/CaptureCoordinator.swift`
- Test: `ios/SmallCuts/SmallCutsTests/CaptureCoordinatorTakeTests.swift`

- [ ] **Step 1: Write caption lifecycle tests**

Add expectations around the existing manual take test:

```swift
XCTAssertEqual(coordinator.caption, "Cut sent. Waiting for the narrator.")

factory.sockets[0].push("""
{
  "contract_version": "1.1.0",
  "scene_id": "scene-1",
  "moment_id": "00000000-0000-4000-8000-000000000001",
  "created_at": "2026-06-15T12:00:00.000+00:00",
  "play_by": "2026-06-15T12:01:00.000+00:00",
  "format": "wav_complete",
  "audio_b64": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=",
  "sample_rate": 16000,
  "narration": "The sidewalk considers its options."
}
""")
await waitUntil("caption updated from SceneAudio") {
    coordinator.caption == "The sidewalk considers its options."
}
XCTAssertFalse(coordinator.awaitingNarration)
```

Use the test socket helpers already present in `CaptureCoordinatorTakeTests.swift`.

- [ ] **Step 2: Set waiting caption on Cut**

In `cutTake()`:

```swift
let sent = await submitUserMoment(endingAt: frame)
awaitingNarration = sent
if sent {
    caption = "Cut sent. Waiting for the narrator."
}
stopFrameCaptureOnly()
```

- [ ] **Step 3: Set narration as soon as SceneAudio arrives**

In `handle(_ event:)`, update `.sceneAudio`:

```swift
case .sceneAudio(let message):
    awaitingNarration = false
    caption = message.narration
    voicePlayer.enqueue(message)
```

Keep `voicePlayer.onClipStarted` as a second confirmation for queued playback.

- [ ] **Step 4: Run iOS tests**

Run:

```bash
DEVELOPER_DIR=/Volumes/mac-studio-ssd/Applications/Xcode.app/Contents/Developer \
xcodebuild test \
  -project ios/SmallCuts/SmallCuts.xcodeproj \
  -scheme SmallCuts \
  -destination 'platform=iOS Simulator,name=iPhone 17,OS=26.5' \
  -derivedDataPath /tmp/smallcuts-derived-sim \
  DEVELOPMENT_TEAM=ZYJ38YVC5F \
  CODE_SIGNING_ALLOWED=NO
```

Expected: simulator suite passes; live-engine smoke remains skipped unless explicitly enabled.

- [ ] **Step 5: Commit**

```bash
git add ios/SmallCuts/SmallCuts/Capture/CaptureCoordinator.swift ios/SmallCuts/SmallCutsTests/CaptureCoordinatorTakeTests.swift
git commit -m "Restore wearer narration captions"
```

## Task 5: Build Longer Honest Glasses Relay Library

**Files:**
- Create: `scripts/build_demo_relay_library.py` if publisher reuse is too awkward.
- Or modify: `scripts/publish_hf_relay.py`
- Document: `docs/regular-pipeline-library-2026-06-15.md`

- [ ] **Step 1: Confirm source clips**

Run:

```bash
find ~/small-cuts-fixtures/videos /private/tmp -maxdepth 3 \( -name '*.mp4' -o -name '*.MP4' -o -name '*.MOV' \) 2>/dev/null | sort
```

Expected: identify the 5-8 real glasses clips to populate the public library.

- [ ] **Step 2: Generate scenes through the regular local glasses pipeline**

Use the local engine/session path for each selected finished video, not Modal and not the judge upload
path. Each scene must be the same artifact shape the glasses path already produces after `Cut!`:

```python
scene = {
    "scene_id": scene_id,
    "title": generated_title,
    "narration": generated_narration,
    "style_key": DEFAULT_STYLE_KEY,
    "created_at": generated_timestamp,
    "visibility": "public",
    "source": "glasses",
    "source_icon": "glasses",
    "media": {
        "frame_url": f"media/{scene_id}/frame.jpg",
        "clip_url": f"media/{scene_id}/clip.mp4",
        "audio_url": f"media/{scene_id}/voice.wav",
        "card_url": f"media/{scene_id}/card.webp",
    },
}
```

Write each scene into a relay staging directory with:

- `media/<scene_id>/frame.jpg`
- `media/<scene_id>/clip.mp4`
- `media/<scene_id>/voice.wav`
- `media/<scene_id>/card.webp`
- `manifest.json` containing contract-valid `NarratedScene` objects with generated title/narration
  and `source="glasses"`.

- [ ] **Step 3: Add glasses-source badge rendering**

In `src/small_cuts/viewer.py`, update the stage/gallery render data so a scene with
`source == "glasses"` or `source_icon == "glasses"` renders a small glasses icon in the top-left
corner of the stage and library tile. Use the existing icon system in `src/small_cuts/_icons.py`
rather than adding an image dependency.

Acceptance:

- Modal/browser uploads have no glasses badge.
- Locally generated glasses cuts have the glasses badge.
- The badge does not change the 9:16 stage layout or cause mobile overflow.

- [ ] **Step 4: Review staged library locally**

Run the viewer against a local fake bucket or copy staged files into the relay cache, then open the local Gradio app:

```bash
SMALL_CUTS_RELAY_BUCKET=build-small-hackathon/small-cuts-scenes \
SMALL_CUTS_RELAY_PREFIX=relay \
SMALL_CUTS_BACKEND=mock \
SMALL_CUTS_TTS_BACKEND=mock \
uv run --no-sync python app.py
```

Expected: library is non-empty, clips are visibly longer than the old 24-frame samples, titles and
captions are generated by the local glasses path, and each glasses-origin item has the small
glasses badge.

- [ ] **Step 5: Publish only after local review**

Run:

```bash
SMALL_CUTS_RELAY_BUCKET=build-small-hackathon/small-cuts-scenes \
SMALL_CUTS_RELAY_PREFIX=relay \
uv run python scripts/build_demo_relay_library.py --sync --delete-extra
```

Expected: bucket relay contains only intentional demo library files under `relay/`.

- [ ] **Step 6: Commit**

```bash
git add src/small_cuts/viewer.py scripts/build_demo_relay_library.py docs/regular-pipeline-library-2026-06-15.md
git commit -m "Populate longer glasses relay library"
```

## Task 6: Verification And Deploy Order

**Files/Services:**
- Local repo.
- iPhone/glasses.
- Modal app `small-cuts-postcut`.
- HF Space `build-small-hackathon/small-cuts-live`.
- HF bucket `build-small-hackathon/small-cuts-scenes`.

- [ ] **Step 1: Run full local Python gate**

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

Expected: all Python checks pass.

- [ ] **Step 2: Run full iOS simulator gate**

Use the `xcodebuild test` command from Task 4.

Expected: all simulator tests pass.

- [ ] **Step 3: Run physical glasses smoke before public library publish**

Acceptance:

- iPhone connects to glasses.
- `Action!` starts capture.
- `Cut!` sends a moment.
- iPhone caption shows waiting state.
- `SceneAudio` returns.
- Caption switches to the generated narration.
- Audio plays through the glasses route.
- The completed local scene has `source="glasses"` when published to the relay bucket.

Do not continue to public library publish if this fails; fix the private live path first.

- [ ] **Step 4: Run local Space upload smoke against Modal before deploying**

Run local app with upload sandbox enabled and the deployed/served Modal URL:

```bash
SMALL_CUTS_ENABLE_UPLOAD_SANDBOX=1 \
SMALL_CUTS_MODAL_API_URL="$SMALL_CUTS_MODAL_API_URL" \
SMALL_CUTS_MODAL_API_TOKEN="$SMALL_CUTS_MODAL_API_TOKEN" \
uv run --no-sync python app.py
```

Browser smoke:

- Sign in with Hugging Face.
- Upload a 5-60 second test clip.
- Confirm generated stage uses `<video>`, not only a still.
- Confirm title, voice, captions, and progress render.
- Confirm a >60 second clip is rejected with a clear message.
- Confirm anonymous viewing still works in a separate/private browser session.

- [ ] **Step 5: Deploy to the org Space only after local tests and Modal POC pass**

Upload source:

```bash
hf upload build-small-hackathon/small-cuts-live . \
  --repo-type=space \
  --exclude '.git/*' \
  --exclude '.venv/*' \
  --exclude 'ios/*' \
  --exclude 'docs/reviews/*' \
  --exclude 'docs/superpowers/*' \
  --exclude 'docs/submission-readiness-*.md' \
  --exclude '__pycache__/*' \
  --exclude '.pytest_cache/*'
```

Set runtime variables:

```bash
hf spaces variables add build-small-hackathon/small-cuts-live -e SMALL_CUTS_RELAY_BUCKET=build-small-hackathon/small-cuts-scenes
hf spaces variables add build-small-hackathon/small-cuts-live -e SMALL_CUTS_RELAY_PREFIX=relay
hf spaces variables add build-small-hackathon/small-cuts-live -e SMALL_CUTS_ENABLE_UPLOAD_SANDBOX=1
hf spaces variables add build-small-hackathon/small-cuts-live -e SMALL_CUTS_UPLOAD_MAX_SECONDS=60
hf spaces variables add build-small-hackathon/small-cuts-live -e SMALL_CUTS_MODAL_API_URL="$SMALL_CUTS_MODAL_API_URL"
hf spaces secrets add build-small-hackathon/small-cuts-live -s SMALL_CUTS_MODAL_API_TOKEN="$SMALL_CUTS_MODAL_API_TOKEN"
hf spaces variables delete build-small-hackathon/small-cuts-live SMALL_CUTS_ENGINE_URL
```

Expected: relay viewer still boots quickly on CPU Basic; upload action calls Modal through the
Space backend; the same short clip that passed against Modal locally works on the org Space.

If Modal POC fails and there is not enough time for a one-line fix, do not switch org hardware.
Disable `SMALL_CUTS_ENABLE_UPLOAD_SANDBOX`, keep the org Space on the safest relay/library posture,
and rely on the demo video plus public relay library for judging. ZeroGPU is a fallback only if
Modal is ruled out deliberately and time remains to test it locally first.

- [ ] **Step 6: Hosted smoke**

Acceptance:

- Space URL loads.
- Relay library appears.
- A human click plays video + voice + captions.
- Glasses-origin clips show the small glasses badge.
- If Modal POC was promoted: upload drawer is available to logged-in HF users.
- If Modal POC was promoted: anonymous viewers can still watch the library.
- If Modal POC was promoted: uploading a short clip produces real title/narration/TTS.
- If Modal POC was promoted: upload result stays on screen and is not interrupted by relay polling.
- Mobile viewport has no overflow.

- [ ] **Step 7: Final docs and submission**

Update:

- `docs/demo-readiness.md`
- README frontmatter links for demo video and social post
- field notes URL

Run the submission analyzer before final submission.

## Fresh Session Execution Prompt

Use this prompt in the new session:

```text
You are Codex in /Volumes/mac-studio-ssd/workspace/small-cuts on branch claude/adoring-clarke-49l3uk.

Do not use the AGENTS teaching loop. Execute, do not quiz.

Read first:
- CLAUDE.md
- src/small_cuts/CLAUDE.md
- docs/demo-readiness.md
- docs/superpowers/plans/2026-06-15-hybrid-judge-upload-final-demo.md
- docs/hackathon-rules.md

Goal:
Implement the hybrid final submission plan. Preserve the non-negotiable private glasses-to-ear path. Add a judge-verifiable finished-video upload path in the submitted Gradio Space, up to 60 seconds by default, with real title/narration/TTS and video replay through Modal. Keep relay/library public viewing via HF bucket. Do not publish or deploy to the Space until local tests and local browser smoke pass.

Important constraints:
- The Space upload path has no glasses, no iOS, and no real-time promise.
- Prove the upload path first through the private Modal app `small-cuts-postcut`.
- Promote the upload path into `build-small-hackathon/small-cuts-live` only if Modal cold/warm timing, bucket artifact writing, and playback smoke pass.
- The glasses/iOS path must restore real-time wearer captions and must not be burdened with a 60-second video payload.
- The wearer UI remains `Action!` and `Cut!` only. Do not add a third publish button.
- Glasses-origin public library items are published from local already-generated scene artifacts after `Cut!`; they do not reach Modal.
- Glasses-origin clips must carry source metadata and show a small glasses icon in the top-left of the Space stage/library tile.
- The public relay library must use honest generated narration/title/TTS, not hand-written captions.
- Do not stage or commit unrelated Xcode project signing noise unless it is required by the task.
- Use apply_patch for manual file edits.
- Run the exact verification gates in the plan before claiming completion.

Preferred order:
1. Modal post-cut POC setup and timing smoke.
2. Space runtime and Modal client tests/implementation.
3. Relay-mode authenticated upload drawer and upload pinning.
4. 60-second upload validation and Modal scene replay.
5. iOS wearer caption restoration.
6. Local gates.
7. Short physical glasses smoke.
8. Longer honest glasses relay library generation with source badge.
9. Promote to org Space only if Modal POC + local verification pass.
10. Hosted smoke and readiness docs.

Commit after each task-sized verified change with short messages.
```

## Self-Review

- Spec coverage: Modal POC, measured promotion gate, glasses smoke first, Space upload as judge verification, 60-second upload, source-badged glasses library clips, real-time iOS captions, no iOS/glasses for upload, no third wearer-side publish button, and no relay-only mock upload are covered.
- Placeholder scan: no task depends on a vague "add tests" or "handle errors"; every task names files and expected commands.
- Type consistency: `upload_scene` is carried through the existing engine UI state dict; `clip_src` and `duration` match `format_stage()` keys already used by the stage renderer.
