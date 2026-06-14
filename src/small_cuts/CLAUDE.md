# CLAUDE.md — `src/small_cuts/` (space / view platform)

Module-local notes for the **Gradio Space + viewer + narration/TTS/title-card** code. Global rules,
the canonical command list, and the architecture live in the **root `CLAUDE.md`** and the **KB**
(`10-projects/small-cuts/space/` and `…/architecture/`). Don't restate them here.

## What's here
- `app.py` (repo root) — HF Space entrypoint. `viewer.py` — the streaming-platform viewer.
- `ui.py` (local dev UI) · `theme.py` (Off-Brand) · `narrator.py` / `tts.py` / `title_card.py` /
  `styles.py` / `frames.py` — the narration pipeline pieces (shared with the engine).
- `demo_seed.py` + `seed_media/` — the hero library (5 real glasses cuts: mp4 + poster + Kokoro mp3).
- `_icons.py` — generated CSS icon masks (from `small_cuts_icon_set`); regenerate if the set changes.

## Run
- See root `CLAUDE.md` → `uv run --no-sync python app.py` (bare `uv run` prunes the `tts` extra).

## Backend selection (env)
- `SMALL_CUTS_BACKEND` = `mock` (default) | `transformers` (`Qwen/Qwen3-VL-8B-Instruct`) | `llama_cpp`.
- `SMALL_CUTS_TTS_BACKEND` = `mock` (default) | `kokoro`. `get_backend()` / `get_tts_backend()` cache
  one instance per key — do **not** construct backends per call (re-loads 16 GB on the Space).

## Viewer modes + layout (`viewer.py`)
- Decided at build time by **`SMALL_CUTS_ENGINE_URL`**: **set** → engine mode (polls `GET /v1/scenes`,
  visibility `PATCH` back); **unset** → upload mode (the Space's local "go live" dropzone).
- **Layout (Review-2):** single centered column — 9:16 stage (the ratio is a hard invariant), a
  display-only progress bar, a control **pill** (rewind/forward = **clip-to-clip**, never intra-clip;
  gr.Audio = play/pause + volume), like (honest **no-count** toggle) + flag, upload-video icon top-right
  (opens the Try-it panel). Header = the auto-title for finished cuts, **"● Happening now"** for live
  engine capture. No REC chip.
- **`SMALL_CUTS_SHOW_FEED`** (default off) revives the dropped narrator-chat feed (a future
  "see transcription" surface for non-live clips).
- **Subtitle/progress sync:** `SUBTITLE_SYNC_JS` advances captions + the progress bar off one clock —
  the embedded voice **duration** (`data-duration`) when known, else ~16 chars/sec; starts at first click.
- **Deferred (Tier-2, fast-follow PR):** swap gr.Audio → a custom slim `<audio>` for the pixel-faithful
  pill + a real seekable bar + true-`currentTime` subtitle sync. Gate it on a live-Space audio test.

## ZeroGPU gotchas (hard-won — see KB `…/space/`)
- `@spaces.GPU` must mark the functions **Gradio binds** (the startup scan walks event handlers);
  decorating inner helpers → worker dies `No CUDA GPUs are available`.
- **No torch forward in the main process ever** — TTS runs inside `@spaces.GPU(duration=…)` workers;
  no main-process pre-warm (kokoro poisons worker forks otherwise).
- Code is hardware-agnostic (`_gpu` no-ops off-Space): dedicated-GPU swap = one
  `hf spaces settings --hardware …`. Iterate: `hf upload …`, `hf spaces variables …`, `hf spaces logs --tail`.

## Design invariant
- The Space is the **view platform + library**, not the capture path. Publishing/visibility happens
  **only here**, never on the glasses (D10). Make it feel like a reference live-streaming platform.
