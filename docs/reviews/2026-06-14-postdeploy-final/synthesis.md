# Post-Deploy Final Review Synthesis

Date: 2026-06-14
Reviewers: Agy, Claude, OpenCode, Cursor Agent
Baseline reviewed: `1104e259affdb7234fffa644993d090b23e25206`

## Accepted Improvements

- Retain post-audio storage tasks with a strong process-level reference.
  - Agy flagged a valid Python lifecycle risk: a shielded task should still be retained until it
    completes, especially after the parent WebSocket task is cancelled.
  - Implemented in `src/small_cuts/engine/session.py` with `_BACKGROUND_STORAGE_TASKS` and
    `_retain_background_storage()`.
  - Tightened `tests/test_engine_session.py::test_disconnect_after_scene_audio_still_publishes_scene`
    to observe retention after disconnect and cleanup after storage completes.

## Rejected Suggestions

- Do not switch the Space to the named Cloudflare tunnel before the physical demo.
  - Direct reads worked, but the Space stayed on "Signal lost" when pointed at the named hostname.
  - The known-good quick tunnel is less elegant but already verified through the Space.
- Do not rewrite the custom player, add SSE, change public visibility semantics, or migrate runtime
  architecture before submission.
  - These are post-hackathon improvements; they add risk without fixing the decisive physical demo
    checks.
- Do not solve the pre-`SceneAudio` disconnect/dedupe gap before the demo.
  - It is real but distinct from the observed symptom. Tailnet makes it lower probability than the
    remaining human/hardware gates.

## Open Questions

- Human Space click: a real desktop browser and iPhone Safari tap must prove video, voice, captions,
  and progress advance together.
- Physical app install: the iPhone must run the latest build and pass simulated-source smoke.
- Physical glasses: Ray-Ban Meta camera streaming and Bluetooth in-ear playback must work together.
- Demo operations: quick tunnel must stay alive or be quickly re-created and re-pointed in the HF
  Space variable.

## Spec Or Code Changes

Implemented after review:

- `src/small_cuts/engine/session.py`
- `tests/test_engine_session.py`

Review artifacts added:

- `docs/reviews/2026-06-14-postdeploy-final/context.md`
- `docs/reviews/2026-06-14-postdeploy-final/prompts/*.md`
- `docs/reviews/2026-06-14-postdeploy-final/reports/*.md`
- `docs/reviews/2026-06-14-postdeploy-final/synthesis.md`

## Reviewer Consensus

- The post-deploy app has no known remaining code blocker for the judged Space or the private engine
  path.
- The storage-after-disconnect symptom is addressed: `SceneAudio` is sent first, scene storage runs
  after audio, and storage now survives client disconnect with both `asyncio.shield()` and a strong
  task reference.
- The highest remaining risks are operational: quick-tunnel availability, cold-start warm-up, real
  human browser audio activation, and physical Ray-Ban/iPhone routing.

## Residual Risks

- A quick tunnel is ephemeral. Keep the re-launch and Space variable update commands ready.
- A first live moment after engine restart can look like a hang. Warm the engine before recording.
- A gate that fires before enough frames are buffered can produce a still instead of `clip.mp4`.
  Move for about four seconds before the hero mark.
- A disconnect before `SceneAudio` is still a separate v1 limitation. Defer until after submission.
