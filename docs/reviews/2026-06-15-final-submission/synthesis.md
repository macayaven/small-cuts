# Final Submission Review Synthesis

Date: 2026-06-15
Reviewers: Claude, OpenCode, Agy
Failed reviewer: Cursor Agent returned an empty report twice with exit code 0.

## Accepted Improvements

- Keep the key-frame thumbnail implementation.
  - Reviewers agreed `pick_key_frame()` is deterministic, bounded, dependency-light, and off the in-ear hot path.
  - `library.store()` still falls back to `scene["image"]` when no clip frames exist.
  - `frame_url` is required by the narrated-scene media contract, while `card_url` is still emitted for title cards, so the gallery preference flip is contract-safe.
- Keep the final submission strategy.
  - The local Mac Studio path best preserves the `offgrid` and `llama` claims.
  - The buffered/Modal POC remains useful v2 evidence but should not replace the final live path.
  - The strongest demo remains glasses-to-ear narration plus the same just-happened cut replaying in the HF Space.
- Keep README wording as CPU viewer/library.
  - This is accurate only when the deployed Space has `SMALL_CUTS_ENGINE_URL` set; that becomes an explicit deploy gate below.

## Rejected Suggestions

- Do not migrate inference to Modal before submission.
- Do not add SSE, rewrite the custom player, alter visibility semantics, or change storage contracts before submission.
- Do not replace the deterministic PIL frame scorer with a learned selector or fixed-aspect crop before submission.

## Open Questions

- HF Space variable state must be checked after deploy: `SMALL_CUTS_ENGINE_URL` must be set so the Space boots as a CPU viewer and does not load the VLM/TTS stack.
- Physical e2e still needs a human-run gate: iPhone over Tailnet, glasses frames, in-ear narration, and the same cut visible on the Space.
- Final README still needs the public demo video and social post links before submission.

## Spec Or Code Changes

- Updated `docs/submission-readiness-2026-06-15.md` so the sample `hf upload` command excludes `docs/submission-readiness-*.md`. The brief is useful internally, but its fallback/employer-signal wording is not part of the public judged artifact.

## Reviewer Consensus

- No material code blocker was found in the thumbnail/title diff.
- The thumbnail change improves the judged library by making it look like a feed of real POV clips rather than generated title cards.
- The highest remaining risks are operational: Space env var correctness, quick-tunnel/read-gate availability, engine warm-up, human browser click playback, and physical glasses/iPhone routing.

## Residual Risks

- If the deployed Space lacks `SMALL_CUTS_ENGINE_URL`, the public README claim of CPU viewer-only becomes false and the app may attempt to load local inference dependencies.
- A quick tunnel can expire. Keep the relaunch and Space-variable update commands ready.
- A cold engine moment is too slow for the hero take. Warm the local engine first.
- Physical Bluetooth/glasses behavior remains the biggest unknown until the live e2e gate.
