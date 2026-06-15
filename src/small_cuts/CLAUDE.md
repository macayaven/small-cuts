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
- Decided at build time by env:
  - **Pure relay mode**: `SMALL_CUTS_RELAY_BUCKET` set and upload sandbox unset. This is the current
    judged-Space posture for
    `build-small-hackathon/small-cuts-live`: viewer-only, CPU Basic, no local model/TTS load, reads a
    finished-scene manifest + media from an HF bucket relay.
  - **Hybrid relay + upload mode**: `SMALL_CUTS_RELAY_BUCKET` and
    `SMALL_CUTS_ENABLE_UPLOAD_SANDBOX=1` set. This is the target final submission posture if judges
    need direct upload verification: relay stays the public library, upload uses real narration/TTS
    on demand, and the Space likely needs ZeroGPU or equivalent runtime for that upload action.
  - **Engine mode**: `SMALL_CUTS_ENGINE_URL` set. Polls `GET /v1/scenes` from an engine/read-gate
    endpoint. Keep this as a local/ops mode unless the current readiness doc explicitly switches back.
  - **Upload mode**: neither relay nor engine env set. Local "try it" dropzone; useful for development
    and fallback demos, not the active public relay architecture.
- **Layout (Review-3 theater):** full-width top bar (Voice-Cut brand mark + upload icon), then a
  two-column **theater** — left: 9:16 stage (ratio is a hard invariant) + display-only progress bar +
  control **pill** (rewind/forward = **clip-to-clip**; gr.Audio stripped to **play/pause + volume**;
  like no-count toggle + flag now **inside** the pill); right: the **Library** rail (gallery). Fits one
  viewport — **no main scrollbar**; a `@media (max-width:860px)` query collapses to one column with a
  horizontal gallery rail on mobile. Header = auto-title for finished cuts / **"● Happening now"** for
  live capture, and is the clickable **back-to-live** affordance (the button is hidden, JS-forwarded).
- **`SMALL_CUTS_SHOW_FEED`** (default off) revives the dropped narrator-chat feed (a future
  "see transcription" surface for non-live clips).
- **One playback clock (`PLAYBACK_SYNC_JS`):** gr.Audio's native `<audio>` is the **sole authority** —
  the muted `<video>` and the captions/progress follow its **play/pause + `currentTime`**, so play runs
  video+voice+captions together and pause freezes all three on the same frame. **Boots PAUSED** (no
  `autoplay` on the player or the video — audible autoplay is browser-blocked anyway): poster + first
  caption + 0% until the first user gesture (tap play). gr.Audio is kept only as the Python→browser
  audio plumbing — `container=False` + `buttons=[]` + CSS strip it to play/pause + volume.
- **Deferred (Tier-2, fast-follow PR):** swap gr.Audio → a custom slim `<audio>` for the pixel-faithful
  gold pill + a real seekable bar. Gate it on a live-Space audio test. (Review-3 took the lower-risk
  strip-and-couple path instead of the swap, since the swap touches Space file-serving.)

## ZeroGPU gotchas (hard-won — see KB `…/space/`)
- In relay or engine viewer-only mode, the Space must not warm Qwen/Kokoro and should stay on
  `cpu-basic`; ZeroGPU is only relevant to upload mode where the Space itself performs narration/TTS.
- `@spaces.GPU` must mark the functions **Gradio binds** (the startup scan walks event handlers);
  decorating inner helpers → worker dies `No CUDA GPUs are available`.
- **No torch forward in the main process ever** — TTS runs inside `@spaces.GPU(duration=…)` workers;
  no main-process pre-warm (kokoro poisons worker forks otherwise).
- Code is hardware-agnostic (`_gpu` no-ops off-Space): dedicated-GPU swap = one
  `hf spaces settings --hardware …`. Iterate: `hf upload …`, `hf spaces variables …`, `hf spaces logs --tail`.

## Design invariant
- The Space is the **view platform + library**, not the capture path. Publishing/visibility happens
  **only here**, never on the glasses (D10). Make it feel like a reference live-streaming platform.
