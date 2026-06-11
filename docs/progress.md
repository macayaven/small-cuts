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
| — | Branch protection on `main` | ⚠️ Carlos reruns the `gh api` command (docs/setup.md) | — |
| — | M1: run eval on DGX Spark, pick narrator model | ⬜ next | docs/implementation-plan.md |
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
6. Run the M1 eval on the DGX Spark (cloud sessions can't reach the tailnet) — one command, docs/implementation-plan.md.
