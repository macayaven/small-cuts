# Demo-Readiness Review Synthesis

Date: 2026-06-14
Reviewers: Agy, Claude, OpenCode, Cursor Agent
Baseline reviewed: `9f7ceea Add just-happened POV clips`

## Accepted Improvements

- Move supplemental frame decode off the in-ear critical path.
  - Implemented in `src/small_cuts/engine/session.py`.
  - The engine now decodes/narrates the selected frame first, sends `SceneAudio`, then decodes supplemental clip frames for storage.
  - Bad supplemental frames log and degrade the Space to a still frame without blocking glasses audio.
  - Regression: `tests/test_engine_session.py::test_bad_supplemental_clip_frame_does_not_block_scene_audio`.
- Reduce iOS live-capture memory and payload pressure.
  - Implemented in `ios/SmallCuts/SmallCuts/Capture/CaptureCoordinator.swift`, `MomentBuilder.swift`, and `GlassesSessionController.swift`.
  - Clip buffer cap reduced from 160 to 32 frames.
  - Glasses stream changed from high/24 fps to high/7 fps, still enough for a 4 s / 12-frame POV sample.
  - Supplemental clip frames encode at 640px/0.72; the selected narration frame remains 1024px/0.9.
  - Regression: `MomentBuilderTests.test_supplementalFramesUseLowerPayloadCap`.
- Fix bounded scene listing so live scenes cannot be hidden by old persisted rows.
  - Implemented in `src/small_cuts/engine/library.py`.
  - `GET /v1/scenes?limit=N` now selects the newest N by `seq`, then returns that window in chronology order for the viewer.
  - Regression: `tests/test_engine_library.py::test_list_scenes_limit_keeps_new_live_scenes_visible`.
- Reuse a read-gate HTTP client across the app lifespan.
  - Implemented in `src/small_cuts/engine/read_gate.py`.
  - Reduces connection churn for HF Space polling and media loads without widening public access.
- Sync contract prose.
  - Updated `moment.schema.json` and `narrated-scene.schema.json` descriptions for timestamped supplemental frames and engine-assembled clips.

## Rejected Suggestions

- Do not lower the selected narration frame below 1024px before the demo.
  - The VLM grounding depends on the selected frame quality; only supplemental viewer frames were reduced.
- Do not enforce `visibility=public` on the public read gate for this demo.
  - The current live demo relies on the public Space seeing newly stored private-default scenes. Treat the live camera as public during the demo and solve auth/publish properly post-submission.
- Do not switch the viewer to SSE before submission.
  - Polling is less elegant, but it is simple and already works through HF Space and Cloudflare. SSE can be a follow-up.
- Do not introduce Modal/GCP runtime dependencies for the judged path.
  - The shortest reliable path is Mac Studio local inference + public read-only Space viewer.

## Open Questions

- Hardware route: confirm returned audio plays in the Ray-Ban Meta glasses while DAT camera streaming remains active.
- Public endpoint: confirm from outside Tailnet that the hostname points at the read gate, not the engine.
- Codec: confirm PyAV can write browser-playable MP4 on the actual Mac Studio process.
- Deployment: confirm the HF Space is running the current viewer code and `SMALL_CUTS_ENGINE_URL` points at the active read-gated HTTPS origin.

## Spec Or Code Changes

Implemented during this review pass:

- `src/small_cuts/engine/session.py`
- `src/small_cuts/engine/library.py`
- `src/small_cuts/engine/read_gate.py`
- `tests/test_engine_session.py`
- `tests/test_engine_library.py`
- `docs/contracts/moment.schema.json`
- `docs/contracts/narrated-scene.schema.json`
- `ios/SmallCuts/SmallCuts/Capture/CaptureCoordinator.swift`
- `ios/SmallCuts/SmallCuts/Capture/MomentBuilder.swift`
- `ios/SmallCuts/SmallCuts/Glasses/GlassesSessionController.swift`
- `ios/SmallCuts/SmallCutsTests/MomentBuilderTests.swift`

## Reviewer Consensus

- The just-happened POV design is directionally correct: frame 0 remains the narration anchor, supplemental frames are only for the public viewer clip, and `clip_url` falls back gracefully.
- The major remaining risks are not model code. They are live operational gates: public endpoint wiring, engine warm-up, hardware audio routing, and making sure the demo is performed with motion.
- A clean/fresh library is good practice, but the query fix means old rows should no longer starve new scenes.

## Residual Risks

- Public read privacy is intentionally not enforced for the demo. Do not capture sensitive content while the public tunnel is up.
- The Space still depends on the Mac Studio engine being up during live mode. Demo video remains the resilience fallback for judging.
- Physical glasses behavior cannot be fully proven by simulator tests. The next decisive test is a real device run.
