Here is the review.

# Final Submission Review — Small Cuts (2026-06-15)

Read-only review of the uncommitted diff on `claude/adoring-clarke-49l3uk`. I read the full diff, traced the contract paths (`library.py`, `viewer.py`, `session.py`, `demo_seed.py`), and re-ran lint + the three changed test modules (all pass).

## Critical Issues

None. No correctness, stability, or submission-blocking defect found in the diff.

## Important Issues

None material. Two non-blocking observations:

- **`pick_key_frame` cost is bounded and off the hot path.** It runs in `store()` over `clip_frames`, which the engine decodes via `asyncio.to_thread` *after* `SceneAudio` is already sent to the ear (`engine/session.py:419`, `:278`). Each frame is downscaled to ≤160px before `FIND_EDGES`/`ImageStat`, and the frame set per moment is contract-bounded — no in-ear latency impact.
- **README repo-map wording** now reads "Gradio CPU viewer/library" while `viewer.py` still carries `@spaces.GPU`/`_gpu()` (which no-op off-Space). This is *consistent* with the documented CPU viewer-only deploy and is more accurate than the old "ZeroGPU" text. Accept.

## Accepted As Is

- **Gallery preference flip** `viewer.py:491` (`card_url or frame_url` → `frame_url or card_url`). Safe: `to_narrated_scene` *always* emits both URLs (`library.py:184-185`), so the flip can never yield an empty thumbnail — it only changes which always-present URL renders. Honors the v1.1.0 media contract. Engine mode only; seed/upload mode uses `local_shelf_items` and is unaffected.
- **`pick_key_frame` scoring** `frames.py`. Deterministic (centrality in-score; `-index` final tiebreak → earliest on ties). Correctly down-weights blown-out/flat frames; `convert("L")` returns a fresh image so source frames reused by `_write_clip_mp4` aren't mutated.
- **Engine poster = key frame** `library.py:133-134`, with `scene["image"]` fallback when no clip frames. Old stored scenes still resolve `frame.jpg`; no migration needed.
- **Thumbnails standardized to `thumbnail((400,540))`** across `make_local_scene` (`viewer.py:586`) and `_seed_scenes` (`:725`) — aspect-preserving, downscale-only, copy-before-mutate, consistent with the engine library so the rail reads as one POV channel.
- **Tests** assert intent (chosen-frame color, key-frame routed to narrator, stage-frame-not-card thumbnail, golden shelf now `frame.jpg`).

## Reject Until After Submission

- `gr.Audio` → custom `<audio>` swap (deferred Tier-2 player).
- SSE/streaming, player rewrite, visibility-semantics or storage changes — frozen by the readiness doc; correctly out of scope.
- Migrating the live runtime to Modal / buffered POC before submission.

## Final Recommendation

**Ship it.** The diff is a tight, well-tested visual-polish change that improves the judged surface (real POV stills instead of generated title cards) with no correctness or stability cost and zero impact on the in-ear latency path. Positioning (`track:wood`; offgrid/offbrand/llama/fieldnotes; no Tiny Titan at 8B) is internally consistent and criteria-aligned.

Remaining risk is **operational, not code**, exactly as the readiness doc states: (1) warm the engine — never use the cold ≈17s first moment as the hero take; (2) verify read-gate posture (`/v1/scenes`→200, `/v1/session` & `PATCH`→403); (3) keep the demo-video fallback ready; (4) confirm README demo/social links resolve and HF metadata carries the four achievement tags before submitting.

One process note: this review re-ran lint on changed files plus the three changed test modules — run the **full** gate (`ruff check . && ruff format --check . && pytest`) once more before the Space upload.

The full review is also saved at `/Users/carlos/.claude/plans/read-only-final-submission-enumerated-panda.md`. I made no changes to the repository.
