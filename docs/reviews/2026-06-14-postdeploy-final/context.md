# Post-Deploy Final Demo Review Context

Date: 2026-06-14
Branch: `claude/adoring-clarke-49l3uk`
Current HEAD: `1104e259affdb7234fffa644993d090b23e25206`

## Product Goal

Small Cuts is a deadpan AI narrator for first-person glasses moments. The winning demo must show:

- Ray-Ban Meta glasses camera path into the iPhone app.
- iPhone writes moments privately to the Mac Studio engine over Tailnet.
- Mac Studio runs local inference/TTS and returns speech to the iPhone/glasses.
- Hugging Face Space is the public judged viewer/library.
- The Space shows the same just-happened POV as a short clip with title, captions, and audio.

## Non-Negotiables

- The e2e glasses -> ear path remains the center of the demo.
- HF Space remains the judged public surface.
- Capture payload is image-frame only in this version; no source audio.
- Public internet must not submit moments or mutate visibility.
- Mac Studio local inference is acceptable and preferred if it is the fastest reliable path.
- Keep fixes simple and demo-safe; no architecture migrations unless the current path is a clear no-go.

## Current Verified State

- Local engine restarted on latest HEAD, listening on `8077`.
- Read gate is listening on `127.0.0.1:8078`.
- Public quick tunnel points to the read gate.
- Public read gate verification:
  - `GET /v1/scenes?limit=3` returns `200`.
  - `GET /v1/session` returns `403`.
  - `PATCH /v1/scenes/example` returns `403`.
- HF Space `build-small-hackathon/small-cuts` is `RUNNING` on `cpu-basic`.
- Space repo SHA after latest upload: `9364ce9ce71f428736ac62da92d5e929ebb7fb73`.
- Space variable `SMALL_CUTS_ENGINE_URL` points at the known-good quick tunnel.
- Real seed POV rehearsal from `src/small_cuts/seed_media/rayuela.mp4`:
  - Private WebSocket returned `ack accepted`.
  - Engine returned `SceneAudio`.
  - Client observed idle status after audio.
  - Scene ID: `3527ae37-325a-4b7e-8ce4-ea0078d5c9a3`.
  - Public `/v1/scenes` includes `frame.jpg`, `card.webp`, `voice.wav`, and `clip.mp4`.
- Browser automation on the Space verified:
  - Desktop renders the real POV scene title and ready `clip.mp4` + `voice.wav`.
  - Mobile viewport `390x844` has no document overflow and ready `clip.mp4` + `voice.wav`.
  - Automated play click fired the playback handler but browser blocked audio with `NotAllowedError`; manual human click remains pending.

## Recent Relevant Fixes

- `src/small_cuts/engine/session.py`
  - Sends `SceneAudio` before viewer-only supplemental clip decode/storage.
  - Shields post-audio storage from cancellation on WebSocket disconnect.
  - Regression: `tests/test_engine_session.py::test_disconnect_after_scene_audio_still_publishes_scene`.
- `src/small_cuts/viewer.py`
  - Custom file-backed `<audio id="sc-voice">` is the playback clock.
  - Play is delegated to trusted DOM gestures instead of Gradio callback execution.
  - Touch/pen `pointerdown` path prevents mobile delayed-click double-toggle.
- `src/small_cuts/engine/read_gate.py`
  - Public allow-list only permits reads for `/v1/scenes`, `/v1/scenes/stream`, and `/media/*`.
- iOS capture path
  - Supplemental frames capped/reduced for payload stability.
  - Glasses stream rate reduced for stability.

## Remaining Decisive Checks

- Human browser click on the Space: video, sound, captions, and progress must advance together.
- Physical iPhone simulated-source smoke after reinstalling latest app.
- Physical Ray-Ban Meta glasses smoke: in-ear narration and Space clip from the same moment.
- Demo video, social post, submission analyzer.

## Review Request

Read the relevant files and current state, then produce a concise markdown report:

1. Critical or important correctness/performance blockers still likely to affect the live demo.
2. Any minimal, non-hacky code or ops changes that should be made before the physical test.
3. Any suggestions that should be explicitly rejected until after submission.
4. Whether the remaining unchecked items in `docs/demo-readiness.md` are correctly classified.
5. Whether the storage-after-disconnect fix is sufficient for the symptom "audio heard, but no Space video/captions."

Stay read-only. Do not edit files. Do not ask for secrets. Do not suggest replacing the architecture unless the current path is demonstrably infeasible.

## Files To Inspect

- `docs/demo-readiness.md`
- `src/small_cuts/engine/session.py`
- `src/small_cuts/engine/app.py`
- `src/small_cuts/engine/library.py`
- `src/small_cuts/engine/read_gate.py`
- `src/small_cuts/viewer.py`
- `ios/SmallCuts/SmallCuts/Capture/CaptureCoordinator.swift`
- `ios/SmallCuts/SmallCuts/Capture/MomentBuilder.swift`
- `ios/SmallCuts/SmallCuts/Glasses/GlassesSessionController.swift`
- `ios/SmallCuts/SmallCutsTests/MomentBuilderTests.swift`
- `tests/test_engine_session.py`
- `tests/test_engine_library.py`
- `tests/test_viewer.py`
