# CLAUDE.md — Small Cuts (root, always-on)

**Small Cuts** turns first-person moments into grounded, cinematic, *spoken* narration using only
**small (≤32B) open models running off-grid**. Goal (single, dual-purpose): **win/place in the
Build Small Hackathon AND/OR make this a portfolio-grade, door-opening applied-AI project.** It is
the strategic successor to *Director's Cut*. Full essence, lineage, and the canonical architecture
live in the **KB** — see Documentation map.

> **Status:** Build Small Hackathon submission (concluded 2026-06-15); now in portfolio polish. Default branch: `main`.

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
- `docs/` — `architecture.md` (the architecture-of-record), `setup.md`, `contracts/` (v1.1.0
  schemas, runtime-validated). Strategy, decisions, and history live in the KB, not the repo.
- `tests/` — pytest incl. golden-sample contract tests.

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
- **HF Space safety:** deploy/test only under personal `macayaven/*` Spaces + buckets, never against
  the `build-small-hackathon/*` org targets. If a Space is `PAUSED` and a restart returns `503`, stop
  all HF Space actions and fall back to local/Modal checks. (Full deployment-safety rules + current
  dev-Space details live in the KB `coordination/` note.)
- **No Space polling loop:** the Gradio Space must not refresh the relay by timer. A successful
  relay publish calls the protected Space hook (`/small-cuts/hooks/relay-scene`), and browser
  clients refresh once from the pushed SSE event (`/small-cuts/events`) through a
  `gr.HTML(js_on_load=...)` custom event bridge, not a hidden button.
- **Gradio 6**: `theme=` is a `launch()` kwarg, **not** `gr.Blocks()`.
- **ruff isort gotcha**: not-yet-existing first-party modules classify as third-party (I001) in
  pre-implementation test files — write imports in post-implementation order, ignore the early fail.
- **Semantic versioning is enforced** (`docs/contracts/`, the Modal API path, releases): MAJOR =
  breaking, MINOR = additive, PATCH = fix. The greenfield narration endpoint is `/v2/narrate`.
- **Contracts** (`docs/contracts/`) are the source of truth: bump schema + golden samples + all
  consumers in **one** PR (lockstep; additive ⇒ MINOR); label `contract-change` ⇒ orchestrator review.
- **No secrets, ever.** 1Password Connect (local dev) + HF Space secrets (deploy); gitleaks in CI.
  Client-facing endpoints use **Tailnet MagicDNS HTTPS** (e.g. `https://mac-studio.tail48bab7.ts.net/…`),
  never raw IPs.

## Coordination
- **Author / director:** Carlos sets the brief, makes the calls, and owns the result. The roles below
  describe the **multi-model process he directs** — not a team that owns the work.
- **Process:** pose a brief → fan it out across independent models for diverse takes (a lead model
  orchestrates; a *different* model family implements, kept distinct from the orchestrator to avoid
  shared blind spots; others review and adversarially verify) → Carlos ratifies the design-of-record.
- **Standing validation panel** (independent peer review, read-only): **GLM 5.2**
  (`opencode run --agent plan`), **GPT-5.5 xhigh** (`codex exec`), **Gemini 3.5-flash-high or 3.1-pro**
  (`gemini -p --approval-mode plan --skip-trust`; pipe the brief via stdin if path-ignore blocks a read).
  Fan briefs out to these for diverse takes; Claude orchestrates + synthesizes; Carlos ratifies.
- **Surfaces:** GitHub Project board **#8**; labels `team-*` + `contract-change`.

## Pointers
- **KB tree** (via `knowledge-base` MCP, under `10-projects/small-cuts/`): `00-overview`,
  `architecture/` (canonical + interactive `index.html`), `space/`, `mobile/`, `inference/`,
  `contracts/`, `product/`, `coordination/`. Predecessor: `10-projects/directors-cut/`.
- **Live device test:** `ios/SmallCuts/RUNBOOK.md`.
- **Models:** `Qwen/Qwen3-VL-8B-Instruct` (narrator) + Kokoro (voice). *(v2 greenfield direction:
  Qwen3-Omni for unified video→text+speech, behind a modular narration backend — design-of-record in
  the KB; not yet as-built.)*

---

## Engineering guidelines (coding discipline)
Bias toward caution over speed; for trivial tasks, use judgment. (Merged from Carlos's request.)

1. **Think before coding.** Don't assume, don't hide confusion, surface tradeoffs. State assumptions
   explicitly; if uncertain, ask. If multiple interpretations exist, present them — don't pick
   silently. If a simpler approach exists, say so and push back when warranted. If something is
   unclear, stop and name it.
2. **Simplicity first.** Minimum code that solves the problem, nothing speculative. No features beyond
   what was asked; no abstractions for single-use code; no unrequested "flexibility"; no error handling
   for impossible scenarios. If 200 lines could be 50, rewrite. Ask: "would a senior engineer call this
   overcomplicated?"
3. **Surgical changes.** Touch only what you must; clean up only your own mess. Don't "improve"
   adjacent code/comments/formatting, don't refactor what isn't broken, match existing style. Remove
   imports/vars/functions *your* change orphaned; mention (don't delete) pre-existing dead code. Every
   changed line should trace to the request.
4. **Goal-driven execution.** Turn tasks into verifiable goals ("add validation" → "write tests for
   invalid inputs, then make them pass"). For multi-step work, state a brief plan with a `verify:` check
   per step, then loop until verified.

Working if: fewer unnecessary diff lines, fewer rewrites from overcomplication, clarifying questions
*before* implementation rather than after mistakes.
