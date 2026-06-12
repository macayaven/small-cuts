# Progress Tracker

| Date | Item | Status | Evidence |
|---|---|---|---|
| 2026-06-11 | Hackathon rules verified from primary sources | ✅ | docs/hackathon-rules.md |
| 2026-06-11 | Product strategy + architecture decided | ✅ | docs/product-strategy.md, docs/architecture.md |
| 2026-06-11 | Repo bootstrap: CI, lint, tests, secret scan, docs | ✅ | .github/workflows/ci.yml |
| 2026-06-11 | Vertical slice: Gradio app w/ mock backend + tests | ✅ | `uv run pytest`, `app.py` |
| 2026-06-11 | KB notes written (mirrored in `kb/`, pending import to canonical KB) | ✅ | kb/*.md |
| 2026-06-11 | Strategy confirmed by Carlos (+ Live Mode requirement added) | ✅ | docs/product-strategy.md |
| 2026-06-11 | `main` branch created (from bootstrap commit) | ✅ | `git push origin claude/adoring-clarke-49l3uk:main` |
| 2026-06-11 | M1 eval harness built + tested | ✅ | `src/small_cuts/eval.py`, `tests/test_eval.py` |
| 2026-06-11 | Self-hosted runner on Spark registered + verified (GB10, CUDA 13.0, uv OK) | ✅ | Actions run 27370230783 (eval-on-spark on `eval/run-001`) |
| — | Branch protection on `main` | ⚠️ Carlos reruns the `gh api` command (docs/setup.md) | — |
| 2026-06-12 | run-004 eval (gemma + Qwen-3B) on Spark, HEIC photos | ✅ | Actions run 27374284507, docs/eval/run-004-scored.md |
| 2026-06-12 | Automated judge: Codex (GPT-5 vision) scores narrations vs actual photos | ✅ | photo relay workflow + codex exec loop, ~7 min/report |
| 2026-06-12 | Prompt A/B judged: v2 "find the story" was a pure loss; reverted+hardened as v3, temp 0.7→0.3 | ✅ | docs/eval/prompt-ab-comparison.md |
| 2026-06-12 | M2 title-card renderer: Claude spec+tests, Codex implementation, 22/22 green | ✅ | docs/specs/title-card.md, src/small_cuts/title_card.py |
| 2026-06-12 | 5 real glasses videos staged (Spark `~/eval-videos`) + relayed locally | ✅ | fetch-eval-photos workflow |
| — | M1: pick narrator model | ⬜ run-005 (prompt v3, temp 0.3, + Qwen-7B) — no candidate meets S>=4&G>=4 bar yet | docs/eval/prompt-ab-comparison.md |
| — | M2: TTS + title card + Off-Brand theme | ⬜ | — |
| — | M3: Space live under hackathon org | ⬜ | — |
| — | M4: demo video + social post + Field Notes | ⬜ | — |
| — | M5: submission | ⬜ deadline June 15 | — |

## Decisions Carlos must make / confirm

1. ~~Confirm Track 2 + quest set~~ ✅ confirmed 2026-06-11, with Live Mode added as a requirement-if-feasible.
2. ~~Solo vs. team~~ ✅ solo.
3. ~~Claim credits~~ ✅ done.
4. Enable branch protection — rerun the `gh api` command now that `main` exists (docs/setup.md).
5. Verify exact submission deadline time + video/post requirements in Discord (Carlos, in progress).
6. ~~Run the M1 eval on the DGX Spark~~ → infrastructure verified working (run 27370230783 reached the GB10). Remaining: stage ~12 personal photos in `/home/carlos/eval-photos` on the Spark, then re-trigger (`gh workflow run eval-on-spark` from a tailnet machine, or push an `eval/**` branch).
