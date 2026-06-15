Read-only review complete. Below is the assessment.

## Blockers
None. The diff is correct, contract-clean, and tested (`169 passed` per context; the new/updated assertions are well-formed and the scoring math checks out — e.g. `test_store_uses_key_frame_for_scene_poster` exercises a flat/detailed/bright triplet where the detailed frame wins on quality ≈0.78 vs ≈0.04).

## Non-Blocking Risks

**Q1 — Key-frame change correctness/performance:** Correct. `pick_key_frame` is deterministic, dependency-light (PIL only, already imported), guards empty input, and preserves the old fallback path in `library.store` (`if clip_frames else scene["image"]`). Performance is acceptable: per-frame work is a 160×160 LANCZOS downscale + `FIND_EDGES` + 2× `ImageStat` (~5–10 ms each on full-res frames), dominated by the existing PyAV decode. Three minor nits:
- The tiebreaker `-item[0]` resolves exact float ties toward the **earlier** frame, which is slightly inconsistent with the docstring's "toward the middle" claim. Immaterial — exact ties are vanishingly rare.
- `Image.Resampling.LANCZOS` is already used elsewhere (`_write_clip_mp4`), so no new Pillow version pin — fine.
- `make_local_scene` changed the upload-mode thumb from a forced 16:9 (`card.resize((480,270))`) to aspect-preserving `thumbnail((400,540))`. `gr.Gallery` handles mixed orientations via `object-fit: cover`, so no break, but a portrait/landscape mix looks slightly less uniform. Matches the seed-library portrait posture, so net-positive.

**Q2 — `frame_url` over `card_url` contract:** No break. `docs/contracts/narrated-scene.schema.json:64-66` requires `frame_url`; `card_url` is optional. `library.to_narrated_scene` still emits **both**, and `card.webp` is still rendered. The change is a pure display-preference swap in one consumer (`shelf_items`); no schema `$id` bump, no golden-sample change, no iOS consumer affected. The stage path (`format_stage` → `frame_src`) already used `frame_url`, so this aligns shelf with stage. `test_poll_engine_renders_the_whole_page` was correctly updated to assert `frame.jpg`.

**README wording risk:** `README.md:123` now says "Gradio CPU viewer/library", but `app.py:30-43` only treats the Space as CPU viewer-only when `SMALL_CUTS_ENGINE_URL` is set. If that env var is unset on the deployed Space, app.py eagerly loads the 8B transformers + Kokoro stack under `@spaces.GPU` — contradicting the README and the readiness doc's "must not load the narrator or TTS stack". Truth of this claim hinges on a Space env var, not on the diff.

**Partial-deploy coupling:** The diff is currently **uncommitted**. The engine needs the `library.store` change to produce new POV posters; the Space needs the `shelf_items` change to prefer them. A mismatch is graceful (both URLs always exist), but suboptimal — both surfaces should ride the same commit.

**Minor:** `docs/submission-readiness-2026-06-15.md` is not in the `hf upload --exclude` list, so it would ship to the Space. No secrets, just internal framing.

## Submission Strategy Assessment

**Q3 — Strongest path under constraints:** Yes. Rejecting Modal (cold-start) and the buffered POC (v2 direction) for the final path is the right call under same-day deadline risk. The glasses → iPhone → Mac Studio → Qwen3-VL-8B → Kokoro → in-ear + Space replay story is the most memorable proof and maps cleanly onto the claimed tags (`track:wood`, `offgrid`, `offbrand`, `llama`, `fieldnotes`). Correctly **not** claiming Tiny Titan (8B > 4B). The fallback (recorded POV clip + local engine + Space replay) preserves the employer signal if Bluetooth/glasses/tunnel wobble. Keeping the Space viewer-only, polling (not SSE), and public-write-blocked is the low-risk posture that matches prior architecture constraints. No rewrite is warranted.

## Defer (explicitly reject until post-submission)
- Modal streaming / parallel-segment orchestration and the buffered POC (correctly punted to v2).
- Custom slim `<audio>` swap for `gr.Audio` (Tier-2, already deferred).
- SSE on the Space (keep polling).
- Replacing the deterministic PIL scorer with a CLIP/learned selector.
- Forcing a fixed gallery thumbnail aspect ratio.
- Migrating historical engine `frame.jpg` files (graceful as-is; new scenes improve incrementally).

## Recommended Next Actions

**Q4 — Verify before live e2e and submission:**

1. **Commit + push the diff** on `claude/adoring-clarke-49l3uk`, then sync to `main` so engine and Space run the same reviewed code.
2. **Confirm the deployed Space has `SMALL_CUTS_ENGINE_URL` set** (`hf spaces variables …`) so it boots in CPU viewer-only mode — this is what makes the README's "CPU viewer/library" wording truthful and prevents an accidental 8B load.
3. **Re-deploy the engine** (restart) so `library.store` starts writing key-frame posters; rebuild the Space so `shelf_items` prefers `frame_url`.
4. **Public read gate:** `GET /v1/scenes?limit=5` → 200; `GET /v1/session` → 403; `PATCH /v1/scenes/example` → 403.
5. **Warm the local engine** with one throwaway moment (cold ≈17 s; warm e2e ≈5.7–6.9 s) before the hero take.
6. **Physical e2e:** iPhone→Tailnet→engine→in-ear narration, and the same cut lands on the Space with `clip.mp4`, `voice.wav`, title, captions, and the new POV `frame.jpg` thumbnail.
7. **Human Space gate:** desktop click and iPhone Safari click both advance video+voice+captions+progress together; no mobile overflow; library shows POV thumbnails + generated titles.
8. **Submission gate:** README demo-video link, social-post link, field-notes link all resolve; HF metadata tags present; submission analyzer passes; add `docs/submission-readiness-2026-06-15.md` to the upload exclude list (optional, tidiness).
