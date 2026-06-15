# CLAUDE.md — Small Cuts (root, always-on)

**Small Cuts** turns first-person moments into grounded, cinematic, *spoken* narration using only
**small (≤32B) open models running off-grid**. Goal (single, dual-purpose): **win/place in the
Build Small Hackathon AND/OR make this a portfolio-grade, door-opening applied-AI project.** It is
the strategic successor to *Director's Cut*. Full essence, lineage, and the canonical architecture
live in the **KB** — see Documentation map.

> **Deadline: 2026-06-15 23:59 UTC.** Branch-of-record: `claude/adoring-clarke-49l3uk` → protected `main`.

---

## Documentation map (READ FIRST — anti-divergence policy)
**One home per fact. Link, never copy.**
- **Operational / as-built** (commands, env vars, conventions, contracts-as-enforced) → **these
  CLAUDE.md files + `docs/`**, versioned with the code.
- **Strategy, lineage, decisions, the architecture, coordination** → **the KB**
  (`knowledge-base` MCP → `knowledge_read`/`knowledge_search`; notes under
  `10-projects/small-cuts/`). The architecture's **single source of truth** is the interactive
  artifact `10-projects/small-cuts/architecture/index.html`.
- The **canonical command list lives once here** (below). Subproject CLAUDE.md files add only
  module-local specifics and **reference** this — they never restate it. (We keep the shared list
  in this always-loaded root rather than a separate `@import`-ed snippet so no extra repo file is
  introduced; `@import` is the mechanism if a dedicated snippet file is added later.)
- **Claude Code auto-memory is a third writer**: operational learnings may land there, but
  **architecture/strategy stays in the KB**.
- **Nested CLAUDE.md are lazy-loaded** (only when you open a file in that subdir):
  `src/small_cuts/` (space) · `src/small_cuts/engine/` (inference) · `ios/SmallCuts/` (mobile) ·
  `docs/contracts/` (contracts).

## Repo map
- `app.py` — HF Space entrypoint (Gradio, ZeroGPU). `requirements.txt` — Space runtime deps.
- `src/small_cuts/` — Python product: `narrator.py` (VLM backends), `tts.py` (Kokoro), `styles.py`
  (6 director styles + grounded prompt v3), `title_card.py`, `theme.py` (Off-Brand), `ui.py`,
  `viewer.py` (streaming viewer; engine + upload modes), `frames.py` (PyAV), `eval.py`.
- `src/small_cuts/engine/` — real-time home-node engine (FastAPI WS `/v1/session`, `library.py`
  sqlite+media, SSE stream). Launch: `python -m small_cuts.engine`.
- `ios/SmallCuts/` — Meta-glasses capture app (XcodeGen, DAT 0.7). See its `RUNBOOK.md`.
- `docs/` — `contracts/` (v1.1.0 schemas), `product/architecture.md` (D1–D9 + the loop),
  `architecture.md`, `product-strategy.md`, `hackathon-rules.md`, `eval/`, `progress.md`, `specs/`.
- `tests/` — pytest incl. golden-sample contract tests. `kb/` — legacy mirror notes (canonical KB
  is the `knowledge-base` MCP).

## Canonical commands (author-once; subprojects reference these)
```bash
# install — CI-equivalent minimal:
uv sync --extra dev
# install — full local (engine + TTS + transformers):
uv sync --extra dev --extra engine --extra tts --extra local

# local gate — MUST mirror CI exactly (all three, in order):
uv run ruff check . && uv run ruff format --check . && uv run pytest

# run the Space/viewer locally (bare `uv run` prunes the tts extra — keep --no-sync):
uv run --no-sync python app.py
# serve on the tailnet:
GRADIO_SERVER_NAME=0.0.0.0 GRADIO_SERVER_PORT=7861 uv run --no-sync python app.py   # http://mac-studio:7861

# run the real-time engine (port 8077; needs `brew install llama.cpp` for llama-server):
SMALL_CUTS_BACKEND=llama_cpp SMALL_CUTS_TTS_BACKEND=kokoro uv run python -m small_cuts.engine
SMALL_CUTS_BACKEND=mock uv run python -m small_cuts.engine          # no-model smoke

# iOS (see ios/SmallCuts/CLAUDE.md + RUNBOOK.md):
DEVELOPER_DIR=/Volumes/mac-studio-ssd/Applications/Xcode.app/Contents/Developer xcodegen

# branch-of-record sync AFTER every squash-merge into main:
git fetch && git merge -s ours origin/main && git push
gh pr merge --auto --squash
```

## Conventions
- **Local gate must mirror CI**: `ruff check` **and** `ruff format --check` **and** `pytest`
  (CI also runs gitleaks). Never trust a piped `gh pr checks --watch` exit code.
- **HF deployment safety override (2026-06-15):** all development, smoke tests, upload tests,
  bucket writes, and Space deploys must use Carlos's personal HF profile (`macayaven/*`) only.
  Do **not** deploy to, poll-test, unpause, mutate variables/secrets on, or write buckets under
  `build-small-hackathon/*` during development. The only remaining org submission Space is
  `build-small-hackathon/small-cuts-buffer-poc`; it is private/paused by Carlos, reserved for final
  submission, and should only be renamed/made public after the personal-profile solution is fully
  proven. Treat `build-small-hackathon/small-cuts-live` and org relay buckets as non-test targets.
- **Gradio 6**: `theme=` is a `launch()` kwarg, **not** `gr.Blocks()`.
- **ruff isort gotcha**: not-yet-existing first-party modules classify as third-party (I001) in
  pre-implementation test files — write imports in post-implementation order, ignore the early fail.
- **Contracts** (`docs/contracts/`, v1.1.0) are the source of truth: bump schema + golden samples +
  all consumers in **one** PR (lockstep minor); label `contract-change` ⇒ orchestrator review.
- **No secrets, ever.** 1Password Connect (local dev) + HF Space secrets (deploy); gitleaks in CI.
  Client-facing endpoints use **Tailnet MagicDNS HTTPS** (e.g. `https://mac-studio.tail48bab7.ts.net/…`),
  never raw IPs.

## Coordination (see KB `10-projects/small-cuts/coordination/`)
- **Roles:** orchestrator = **Opus 4.8** (assumed the lead vacated by **Fable 5**, pending Carlos's
  confirmation) · implementer = **Codex (GPT-5.x)** · reviewer = **GLM / opencode** · eval judge =
  **agy (Gemini)** · optional independent check = **GPT-5.x red-teams the plan**. Keep orchestrator ≠
  implementer (different model families).
- **Peers:** codex, agy, agent, opencode, + Carlos.
- **Surfaces:** GitHub Project board **#8**; epics **#36** team-space / **#37** team-mobile /
  **#38** team-inference; labels `team-*` + `contract-change`.

## Pointers
- **KB tree** (via `knowledge-base` MCP, under `10-projects/small-cuts/`): `00-overview`,
  `architecture/` (canonical + interactive `index.html`), `space/`, `mobile/`, `inference/`,
  `contracts/`, `product/`, `coordination/`. Predecessor: `10-projects/directors-cut/`.
- **Live device test:** `ios/SmallCuts/RUNBOOK.md`. **Hackathon rules:** `docs/hackathon-rules.md`.
- **HF targets:** development/testing happens only under `macayaven/*`; final submission reserves
  `build-small-hackathon/small-cuts-buffer-poc`. **Model:** `Qwen/Qwen3-VL-8B-Instruct` (M1 pick).
