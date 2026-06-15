# Hybrid Judge Upload And Final Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the judge-upload path in an isolated personal ZeroGPU Space, then promote the measured working path into the submitted org Space while preserving the non-negotiable private glasses-to-ear live narration demo.

**Architecture:** Keep four flows separate while validating them in order. The personal ZeroGPU POC (`macayaven/small-cuts-zerogpu-poc`) proves upload inference without risking the submitted Space. The submitted org Space (`build-small-hackathon/small-cuts-live`) keeps relay/library viewing and receives the upload path only after POC smoke passes. The glasses/iOS path remains private and real-time to the wearer's ear; if ZeroGPU post-cut inference is fast enough, glasses can also publish finished videos through the bucket/hook path for the public library.

**Tech Stack:** Gradio, Hugging Face Spaces, personal ZeroGPU POC, org Space, HF bucket relay, PyAV/H.264 MP4 generation, Qwen3-VL-8B, Kokoro TTS, SwiftUI iOS app, FastAPI engine, Ray-Ban Meta glasses.

---

## Current Timebox

Plan timestamp: 2026-06-15 12:31 UTC / 14:31 CEST.

Submission deadline: 2026-06-15 23:59 UTC / 2026-06-16 01:59 CEST.

Time remaining at plan update: about 11 h 28 m.

## Decisions Locked By This Plan

- Do a short physical glasses smoke before public library population. This confirms the non-negotiable glasses -> iPhone -> Mac engine -> in-ear narration path before spending time polishing public artifacts.
- Do not expand the iOS real-time WebSocket payload to 20 seconds just for the Space. That would risk upload latency and the ear-first experience.
- Implement the 20-second video upload as a Space-only judge verification path. It processes a completed uploaded clip, generates title/narration/TTS, and replays the uploaded clip with synced captions.
- Prove the upload path first in a personal private ZeroGPU Space named
  `macayaven/small-cuts-zerogpu-poc`. Do not risk the submitted org Space until cold/warm upload
  timing and playback behavior are measured.
- The submitted Space should be hybrid:
  - relay viewer/library from `SMALL_CUTS_RELAY_BUCKET`;
  - upload drawer enabled by `SMALL_CUTS_ENABLE_UPLOAD_SANDBOX=1`.
- The upload drawer must use real narration/TTS, not mock output. If the personal POC is good, promote
  the same path to the org Space and run `build-small-hackathon/small-cuts-live` on `zero-a10g`; keep
  the relay viewer fast so the page remains useful even if GPU quota/cold start slows the upload action.
- If ZeroGPU post-cut timings are acceptable, finished glasses videos can later use the same
  bucket-triggered post-cut inference path for the public library. Local Mac Studio inference remains
  the real-time in-ear path regardless.
- Public library clips should be longer and generated honestly from real glasses clips with the same model prompt/title/TTS path, not hand-written captions.

## File Responsibilities

- `app.py`: decide whether the Space must load real model backends for upload even when relay mode is enabled.
- `src/small_cuts/viewer.py`: hybrid relay + upload UI, 20-second upload validation, uploaded-video stage replay, upload pinning so relay polling does not overwrite the judge's uploaded result.
- `src/small_cuts/engine/library.py`: reusable MP4 writer options for upload/library clip generation.
- `src/small_cuts/frames.py`: optional duration helper and bounded frame sampling tests.
- `tests/test_app_entrypoint.py`: Space backend selection in hybrid relay+upload mode.
- `tests/test_viewer.py`: upload drawer visibility, 20-second cap, uploaded clip replay, relay polling not interrupting an uploaded result.
- `tests/test_engine_library.py`: MP4 writer FPS/blend behavior for longer clips.
- Personal POC Space `macayaven/small-cuts-zerogpu-poc`: private, disposable ZeroGPU target for
  upload inference timing and browser smoke.
- `scripts/measure_zerogpu_upload.py`: optional timing harness if browser-only timing is too manual.
- `ios/SmallCuts/SmallCuts/Capture/CaptureCoordinator.swift`: restore explicit wearer captions/status for the real-time glasses path.
- `ios/SmallCuts/SmallCuts/UI/ContentView.swift`: only if the caption pane needs copy/layout adjustment.
- `ios/SmallCuts/SmallCutsTests/CaptureCoordinatorTakeTests.swift`: caption state tests for Cut -> waiting -> SceneAudio.
- `scripts/publish_hf_relay.py` or a new `scripts/build_demo_relay_library.py`: publish only selected, controlled longer clips to the relay bucket.
- `docs/demo-readiness.md`: keep the active state updated after each gate.

## Task 0: Personal ZeroGPU Upload POC

**Files/Services:**
- Space: `macayaven/small-cuts-zerogpu-poc`
- Source: current checkout
- Modify only if needed: `README.md` Space metadata, Space variables/secrets
- Evidence: update `docs/demo-readiness.md`

- [ ] **Step 1: Create or reset the private personal POC Space**

Run:

```bash
hf repo create macayaven/small-cuts-zerogpu-poc --repo-type=space --space-sdk=gradio --private --yes
hf spaces settings macayaven/small-cuts-zerogpu-poc --hardware zero-a10g
```

Expected: a private personal Gradio Space exists and reports ZeroGPU hardware. If the repo already
exists, skip `repo create` and run only the hardware command.

- [ ] **Step 2: Upload the current app source to the personal POC**

Run:

```bash
hf upload macayaven/small-cuts-zerogpu-poc . \
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

Expected: upload succeeds and the personal POC rebuilds independently of the org Space.

- [ ] **Step 3: Configure POC upload mode only**

Run:

```bash
hf spaces variables delete macayaven/small-cuts-zerogpu-poc SMALL_CUTS_RELAY_BUCKET || true
hf spaces variables delete macayaven/small-cuts-zerogpu-poc SMALL_CUTS_ENGINE_URL || true
hf spaces variables set macayaven/small-cuts-zerogpu-poc SMALL_CUTS_ENABLE_UPLOAD_SANDBOX=1
hf spaces variables set macayaven/small-cuts-zerogpu-poc SMALL_CUTS_UPLOAD_MAX_SECONDS=20
hf spaces variables set macayaven/small-cuts-zerogpu-poc SMALL_CUTS_BACKEND=transformers
hf spaces variables set macayaven/small-cuts-zerogpu-poc SMALL_CUTS_TTS_BACKEND=kokoro
```

Expected: the POC runs the self-contained upload path with real Qwen/Kokoro and no relay dependency.

- [ ] **Step 4: Smoke the POC manually**

Open:

```text
https://huggingface.co/spaces/macayaven/small-cuts-zerogpu-poc
```

Acceptance:

- Space loads without using local engine or Cloudflare.
- Upload drawer is visible.
- A 5-20 second clip produces a generated title, generated narration, voice, captions, and replayable
  video.
- A >20 second clip is rejected clearly.
- The output is grounded enough to be judge-facing.

- [ ] **Step 5: Measure cold and warm upload timings**

Record at least three runs:

```text
cold_start_s:
warm_upload_1_s:
warm_upload_2_s:
video_duration_s:
model_backend:
tts_backend:
result_quality:
```

Promotion threshold:

- Cold run can be slow but must complete without crash.
- Warm 5-20 second uploads should complete reliably enough for judging. Target: under 60 seconds;
  acceptable fallback: under 120 seconds if the page clearly shows progress and the demo video covers
  the live experience.
- Narration must be real Qwen output and audio must be real Kokoro output.

- [ ] **Step 6: Decide promotion**

If POC passes, promote the code/config to `build-small-hackathon/small-cuts-live` in Task 6.

If POC fails, keep `build-small-hackathon/small-cuts-live` as relay/library plus demo video, and do
not burn remaining time debugging ZeroGPU unless the failure is a one-line configuration issue.

- [ ] **Step 7: Update readiness evidence**

Append timing and promotion decision to `docs/demo-readiness.md` under the current architecture
override before moving to Task 1.

## Task 1: Hybrid Runtime Selection

**Files:**
- Modify: `app.py`
- Test: `tests/test_app_entrypoint.py`

- [ ] **Step 1: Write failing tests for hybrid relay+upload mode**

Add this test to `tests/test_app_entrypoint.py`:

```python
def test_space_relay_with_upload_sandbox_uses_real_backends(monkeypatch):
    monkeypatch.setenv("SPACE_ID", "build-small-hackathon/small-cuts-live")
    monkeypatch.delenv("SMALL_CUTS_ENGINE_URL", raising=False)
    monkeypatch.setenv("SMALL_CUTS_RELAY_BUCKET", "build-small-hackathon/small-cuts-scenes")
    monkeypatch.setenv("SMALL_CUTS_ENABLE_UPLOAD_SANDBOX", "1")
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)
    monkeypatch.delenv("SMALL_CUTS_TTS_BACKEND", raising=False)
    monkeypatch.setitem(sys.modules, "spaces", None)

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    spec = importlib.util.spec_from_file_location("_small_cuts_test_app_hybrid", app_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert os.environ.get("SMALL_CUTS_BACKEND") == "transformers"
    assert os.environ.get("SMALL_CUTS_TTS_BACKEND") == "kokoro"
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
uv run pytest tests/test_app_entrypoint.py::test_space_relay_with_upload_sandbox_uses_real_backends -q
```

Expected before implementation: FAIL because relay mode currently keeps the Space viewer-only and does not set real upload backends.

- [ ] **Step 3: Implement hybrid runtime selection**

Change the top-level mode logic in `app.py` to this shape:

```python
ENGINE_MODE = bool(os.environ.get("SMALL_CUTS_ENGINE_URL", "").strip())

from small_cuts.hf_relay import RELAY_BUCKET_ENV  # noqa: E402

RELAY_MODE = bool(os.environ.get(RELAY_BUCKET_ENV, "").strip())
UPLOAD_SANDBOX_MODE = os.environ.get("SMALL_CUTS_ENABLE_UPLOAD_SANDBOX", "").strip().lower() in (
    "1",
    "true",
    "yes",
)
VIEWER_ONLY_MODE = (ENGINE_MODE or RELAY_MODE) and not UPLOAD_SANDBOX_MODE
NEEDS_LOCAL_INFERENCE = (not ENGINE_MODE and not RELAY_MODE) or UPLOAD_SANDBOX_MODE

if ON_SPACE and NEEDS_LOCAL_INFERENCE:
    os.environ.setdefault("SMALL_CUTS_BACKEND", "transformers")
    os.environ.setdefault("SMALL_CUTS_TTS_BACKEND", "kokoro")
```

Keep the eager narrator load under `if NEEDS_LOCAL_INFERENCE:`. Do not pre-warm Kokoro in the main process.

- [ ] **Step 4: Verify entrypoint tests**

Run:

```bash
uv run pytest tests/test_app_entrypoint.py -q
```

Expected: all entrypoint tests pass.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app_entrypoint.py
git commit -m "Enable hybrid relay upload runtime"
```

## Task 2: Space Upload Drawer In Relay Mode

**Files:**
- Modify: `src/small_cuts/viewer.py`
- Test: `tests/test_viewer.py`

- [ ] **Step 1: Write tests for upload availability and pinning**

Add pure helper tests that do not require launching the full Gradio app:

```python
def test_upload_sandbox_enabled_in_relay_mode(monkeypatch):
    monkeypatch.setenv("SMALL_CUTS_ENABLE_UPLOAD_SANDBOX", "1")
    assert viewer.upload_sandbox_enabled() is True


def test_upload_scene_pins_stage_against_relay_poll(monkeypatch):
    upload_scene = {
        "scene_id": "local-upload-1",
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
    assert state["upload_scene"]["scene_id"] == "local-upload-1"
```

- [ ] **Step 2: Add a small helper for upload mode**

In `src/small_cuts/viewer.py`, add:

```python
def upload_sandbox_enabled() -> bool:
    return os.environ.get("SMALL_CUTS_ENABLE_UPLOAD_SANDBOX", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
```

- [ ] **Step 3: Keep relay polling from interrupting uploaded results**

Extend `_engine_ui_state()` and `_pack_engine_ui_state()` with an `upload_scene` field:

```python
def _engine_ui_state(value: Any) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    scenes = data.get("scenes")
    return {
        "scenes": scenes if isinstance(scenes, list) else [],
        "pinned_id": data.get("pinned_id"),
        "current_id": data.get("current_id"),
        "playing_id": data.get("playing_id"),
        "upload_scene": data.get("upload_scene") if isinstance(data.get("upload_scene"), dict) else None,
    }
```

In `poll_engine()`, if `state["upload_scene"]` is present, update shelf/feed from relay as usual but return `gr.skip()` for header, stage, and audio so the judge's uploaded result stays on screen until Back to live clears it.

- [ ] **Step 4: Show the upload drawer when relay mode is active**

In `build_viewer_app()`, replace `if client is None:` checks that gate the upload controls with:

```python
upload_enabled = client is None or upload_sandbox_enabled()
```

Use a `gr.State(DEFAULT_STYLE_KEY)` for upload style whenever `upload_enabled` is true. The public UI should still present one voice/style, not a distracting director menu.

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
git commit -m "Show judge upload in relay viewer"
```

## Task 3: 20-Second Finished Video Uploads

**Files:**
- Modify: `src/small_cuts/viewer.py`
- Modify: `src/small_cuts/engine/library.py`
- Test: `tests/test_viewer.py`
- Test: `tests/test_engine_library.py`

- [ ] **Step 1: Write tests for upload duration and clip replay**

Add tests in `tests/test_viewer.py`:

```python
def test_upload_video_cap_defaults_to_twenty_seconds(monkeypatch):
    monkeypatch.delenv("SMALL_CUTS_UPLOAD_MAX_SECONDS", raising=False)
    assert viewer.upload_max_seconds() == 20.0


def test_make_local_scene_keeps_uploaded_clip_src():
    frame = Image.new("RGB", (120, 200), "black")
    card = Image.new("RGB", (1280, 720), "white")
    scene = viewer.make_local_scene(
        frame,
        card,
        "A sentence.",
        "deadpan",
        clip_src="/gradio_api/file=/tmp/clip.mp4",
        duration=12.5,
    )
    assert scene["clip_src"].endswith("clip.mp4")
    assert scene["duration"] == 12.5
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

- [ ] **Step 2: Add upload constants and duration helpers**

In `src/small_cuts/viewer.py`, add:

```python
UPLOAD_MAX_SECONDS_ENV = "SMALL_CUTS_UPLOAD_MAX_SECONDS"
UPLOAD_CLIP_FPS = 8
UPLOAD_MAX_CLIP_FRAMES = 160
GENERATED_VIDEO_DIR = Path(tempfile.gettempdir()) / "small_cuts_upload_clips"


def upload_max_seconds() -> float:
    raw = os.environ.get(UPLOAD_MAX_SECONDS_ENV, "20")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 20.0
```

Add a PyAV duration helper:

```python
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

- [ ] **Step 3: Make the MP4 writer configurable**

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

Existing callers keep the default blend. Upload code passes `blend_steps=0` so a 20-second sampled upload does not double its apparent duration.

- [ ] **Step 4: Stage uploaded video as browser-safe MP4**

In `src/small_cuts/viewer.py`, add:

```python
def _write_uploaded_clip(video_path: str, scene_id: str) -> tuple[str | None, float | None]:
    duration = _video_duration_s(video_path)
    if duration is not None and duration > upload_max_seconds() + 0.25:
        raise gr.Error(f"Please upload a clip up to {upload_max_seconds():.0f} seconds.")
    frames = sample_frames(
        video_path,
        every_n_seconds=1 / UPLOAD_CLIP_FPS,
        max_frames=UPLOAD_MAX_CLIP_FRAMES,
    )
    if len(frames) < 2:
        return None, duration
    GENERATED_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    target = GENERATED_VIDEO_DIR / f"{scene_id}.mp4"
    from small_cuts.engine.library import _write_clip_mp4

    _write_clip_mp4(target, frames, fps=UPLOAD_CLIP_FPS, blend_steps=0)
    gr.set_static_paths([GENERATED_AUDIO_DIR, GENERATED_VIDEO_DIR, demo_seed.SEED_DIR])
    return f"/gradio_api/file={target}", min(duration or upload_max_seconds(), upload_max_seconds())
```

- [ ] **Step 5: Store clip source in local upload scenes**

Change `make_local_scene()` signature:

```python
def make_local_scene(
    frame: Image.Image | None,
    card: Image.Image,
    narration: str,
    style_key: str,
    *,
    clip_src: str | None = None,
    duration: float | None = None,
) -> dict[str, Any]:
```

Include `clip_src` and `duration` when present.

- [ ] **Step 6: Use video clip in `_go_live_handler()`**

Inside `_go_live_handler()`, when `video_path` is present:

```python
scene_id = f"local-{uuid.uuid4().hex[:12]}"
clip_src, clip_duration = _write_uploaded_clip(video_path, scene_id)
frame = pick_key_frame(sample_frames(video_path, every_n_seconds=0.75, max_frames=32))
...
scene = make_local_scene(
    frame,
    card,
    narration,
    style_key,
    clip_src=clip_src,
    duration=clip_duration,
)
scene["scene_id"] = scene_id
```

Keep still-image fallback for empty video or decode failure, but the success path must render `<video>` through `render_stage_html(... clip_src=payload["clip_src"])`.

- [ ] **Step 7: Verify tests**

Run:

```bash
uv run pytest tests/test_viewer.py tests/test_engine_library.py -q
```

Expected: tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/small_cuts/viewer.py src/small_cuts/engine/library.py tests/test_viewer.py tests/test_engine_library.py
git commit -m "Support 20 second judge video uploads"
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

## Task 5: Build Longer Honest Relay Library

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

- [ ] **Step 2: Generate scenes through the same upload pipeline**

Use the same functions from Task 3 for each selected finished video:

```python
frame = pick_key_frame(sample_frames(video_path, every_n_seconds=0.75, max_frames=32))
card, narration = _narrate_core(frame, DEFAULT_STYLE_KEY, "", EMPTY_VIDEO_CAPTION)
speech = speak(narration)
clip_src, duration = _write_uploaded_clip(str(video_path), scene_id)
title = derive_title(narration)
```

Write each scene into a relay staging directory with:

- `media/<scene_id>/frame.jpg`
- `media/<scene_id>/clip.mp4`
- `media/<scene_id>/voice.wav`
- `media/<scene_id>/card.webp`
- `manifest.json` containing contract-valid `NarratedScene` objects with generated title/narration.

- [ ] **Step 3: Review staged library locally**

Run the viewer against a local fake bucket or copy staged files into the relay cache, then open the local Gradio app:

```bash
SMALL_CUTS_RELAY_BUCKET=build-small-hackathon/small-cuts-scenes \
SMALL_CUTS_RELAY_PREFIX=relay \
SMALL_CUTS_BACKEND=mock \
SMALL_CUTS_TTS_BACKEND=mock \
uv run --no-sync python app.py
```

Expected: library is non-empty, clips are visibly longer than the old 24-frame samples, titles and captions are generated by the model path.

- [ ] **Step 4: Publish only after local review**

Run:

```bash
SMALL_CUTS_RELAY_BUCKET=build-small-hackathon/small-cuts-scenes \
SMALL_CUTS_RELAY_PREFIX=relay \
uv run python scripts/build_demo_relay_library.py --sync --delete-extra
```

Expected: bucket relay contains only intentional demo library files under `relay/`.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_demo_relay_library.py docs/regular-pipeline-library-2026-06-15.md
git commit -m "Populate longer relay library"
```

## Task 6: Verification And Deploy Order

**Files/Services:**
- Local repo.
- iPhone/glasses.
- Personal POC Space `macayaven/small-cuts-zerogpu-poc`.
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

Do not continue to public library publish if this fails; fix the private live path first.

- [ ] **Step 4: Run local Space upload smoke before deploying**

Run local app with upload sandbox enabled:

```bash
SMALL_CUTS_ENABLE_UPLOAD_SANDBOX=1 \
SMALL_CUTS_BACKEND=mock \
SMALL_CUTS_TTS_BACKEND=mock \
uv run --no-sync python app.py
```

Browser smoke:

- Upload a 5-20 second test clip.
- Confirm generated stage uses `<video>`, not only a still.
- Confirm title, voice, captions, and progress render.
- Confirm a >20 second clip is rejected with a clear message.

- [ ] **Step 5: Deploy to the org Space only after local tests and personal POC pass**

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
hf spaces variables set build-small-hackathon/small-cuts-live SMALL_CUTS_RELAY_BUCKET=build-small-hackathon/small-cuts-scenes
hf spaces variables set build-small-hackathon/small-cuts-live SMALL_CUTS_RELAY_PREFIX=relay
hf spaces variables set build-small-hackathon/small-cuts-live SMALL_CUTS_ENABLE_UPLOAD_SANDBOX=1
hf spaces variables set build-small-hackathon/small-cuts-live SMALL_CUTS_UPLOAD_MAX_SECONDS=20
hf spaces variables delete build-small-hackathon/small-cuts-live SMALL_CUTS_ENGINE_URL
```

If Task 0 POC passed and upload inference is being promoted, switch the org Space to ZeroGPU:

```bash
hf spaces settings build-small-hackathon/small-cuts-live --hardware zero-a10g
```

Expected: relay viewer still boots quickly; upload action schedules GPU work; the same short clip that
passed on the personal POC works on the org Space.

If Task 0 POC failed, do not switch org hardware. Keep the org Space on the safest relay/library
posture and rely on the demo video plus public relay library for judging.

- [ ] **Step 6: Hosted smoke**

Acceptance:

- Space URL loads.
- Relay library appears.
- A human click plays video + voice + captions.
- If Task 0 was promoted: upload drawer is available.
- If Task 0 was promoted: uploading a short clip produces real title/narration/TTS.
- If Task 0 was promoted: upload result stays on screen and is not interrupted by relay polling.
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
Implement the hybrid final submission plan. Preserve the non-negotiable private glasses-to-ear path. Add a judge-verifiable finished-video upload path in the submitted Gradio Space, up to 20 seconds, with real title/narration/TTS and video replay. Keep relay/library public viewing via HF bucket. Do not publish or deploy to the Space until local tests and local browser smoke pass.

Important constraints:
- The Space upload path has no glasses, no iOS, and no real-time promise.
- Prove the upload path first in the private personal ZeroGPU POC Space `macayaven/small-cuts-zerogpu-poc`.
- Promote the upload path into `build-small-hackathon/small-cuts-live` only if the personal POC passes cold/warm timing and playback smoke.
- The glasses/iOS path must restore real-time wearer captions and must not be burdened with a 20-second video payload.
- The public relay library must use honest generated narration/title/TTS, not hand-written captions.
- Do not stage or commit unrelated Xcode project signing noise unless it is required by the task.
- Use apply_patch for manual file edits.
- Run the exact verification gates in the plan before claiming completion.

Preferred order:
1. Personal ZeroGPU upload POC setup and timing smoke.
2. Hybrid runtime selection tests and implementation.
3. Relay-mode upload drawer and upload pinning.
4. 20-second upload video replay and MP4 normalization.
5. iOS wearer caption restoration.
6. Local gates.
7. Short physical glasses smoke.
8. Longer honest relay library generation.
9. Promote to org Space only if POC + local verification pass.
10. Hosted smoke and readiness docs.

Commit after each task-sized verified change with short messages.
```

## Self-Review

- Spec coverage: personal ZeroGPU POC, measured promotion gate, glasses smoke first, Space upload as judge verification, 20-second upload, longer library clips, real-time iOS captions, no iOS/glasses for upload, and no relay-only mock upload are covered.
- Placeholder scan: no task depends on a vague "add tests" or "handle errors"; every task names files and expected commands.
- Type consistency: `upload_scene` is carried through the existing engine UI state dict; `clip_src` and `duration` match `format_stage()` keys already used by the stage renderer.
