# Final Submission Review Context

Date: 2026-06-15
Branch: `claude/adoring-clarke-49l3uk`

## Objective

Small Cuts is preparing the final Build Small Hackathon submission. The non-negotiable product story is:

```text
Ray-Ban Meta glasses -> iPhone -> local Mac Studio engine -> small VLM narration -> Kokoro TTS -> in-ear audio + HF Space replay/library
```

The Hugging Face Space is the judged public surface. The Space should remain CPU viewer-only; local hardware runs inference/TTS for the live path. Capture is image-frame only for this version.

## Current Final Recommendation

Submit the current architecture. Do not migrate the final path to Modal or the buffered POC before submission. Modal remains useful evidence for future v2 streaming and parallel segment orchestration, but the final live demo should emphasize the real glasses-to-ear loop plus polished HF Space replay.

Primary track: `track:wood`.

Claimed achievements:

- `achievement:offgrid`
- `achievement:offbrand`
- `achievement:llama`
- `achievement:fieldnotes`

Do not claim Tiny Titan.

## Current Diff To Review

The current uncommitted diff is intentionally small:

- `src/small_cuts/frames.py`: adds deterministic `pick_key_frame()`.
- `src/small_cuts/engine/library.py`: stores the selected key frame as `frame.jpg` for scene posters.
- `src/small_cuts/viewer.py`: gallery prefers `frame_url` before `card_url`; upload-mode local thumbnails use the stage frame instead of the title card; video upload narration uses `pick_key_frame()`.
- `src/small_cuts/ui.py`: video upload narration uses `pick_key_frame()`.
- `tests/test_frames.py`, `tests/test_engine_library.py`, `tests/test_viewer.py`: regression coverage.
- `README.md`: corrects the Space entrypoint wording from ZeroGPU to CPU viewer/library.
- `docs/submission-readiness-2026-06-15.md`: records the final recommendation, remaining gates, and fallback posture.

## Evidence Already Collected

- Full Python gate passed after the key-frame change: `169 passed, 3 warnings`.
- Local browser smoke on `127.0.0.1:7862` showed a working viewer with real POV library thumbnails, no document overflow, and a stage video.
- Key-frame contact sheets were generated from seed clips and staged real glasses videos under `/tmp/small-cuts-keyframes-v2`.
- Previous multi-review synthesis found no remaining code blocker after the storage-after-disconnect fix; remaining risks were operational: quick tunnel, warm-up, human Space click, and physical glasses/iPhone routing.
- Official hackathon constraints require a Gradio Space, model sizes <=32B, a short demo video, and a social post. The submission should optimize for Thousand Token Wood, Best Demo, Off-Brand, Off the Grid, Llama, and Field Notes.

## Known Constraints

- No secrets.
- Do not propose architecture rewrites before submission unless the current path is clearly not viable.
- Keep public writes blocked through the read gate.
- Keep Space viewer-only unless there is a decisive correctness reason to change.
- The final answer should be actionable: issues only if they matter for correctness, performance, stability, narrative quality, or submission chance.

## Questions For Reviewers

1. Is the key-frame thumbnail implementation correct enough for final submission, or does it introduce a material bug/regression?
2. Does preferring `frame_url` over `card_url` in the gallery honor the viewer and engine contracts?
3. Is the final recommendation in `docs/submission-readiness-2026-06-15.md` aligned with the hackathon criteria and prior architecture constraints?
4. What are the highest remaining risks before the live e2e and submission?
5. Which suggestions should explicitly be rejected until after submission?
