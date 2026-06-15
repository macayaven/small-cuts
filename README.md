---
title: Small Cuts
emoji: 🎬
colorFrom: indigo
colorTo: purple
sdk: gradio
sdk_version: 6.18.0
app_file: app.py
pinned: true
license: mit
short_description: A deadpan narrator for your life, from small open models.
tags:
  - track:wood
  - achievement:offgrid
  - achievement:offbrand
  - achievement:llama
  - achievement:fieldnotes
---

# Small Cuts 🎬

> *"And that was the moment Carlos realized the coffee had been decaf all along."*

**Small Cuts** turns first-person moments into grounded, cinematic, **spoken** narration —
an omniscient, slightly-too-honest narrator in the spirit of *The Invention of Lying* —
using only **small (≤32B) open models**. No script, no cloud LLM: a small vision-language
model watches your moment and a small TTS speaks the line, the way a film narrator would
if your life were the film.

There is exactly **one narrator** — a single deadpan, unnamed voice. No menus, no
director to pick. You point at what's happening; it tells you what it means.

This is the **challenger submission** for the
[Build Small Hackathon](https://huggingface.co/build-small-hackathon)
("Small Models, Big Adventures" — Gradio × Hugging Face, submissions close
**June 15, 2026, 23:59 UTC**), the strategic successor to the original
*Director's Cut* project.

## The soul of it — the real-time loop

Small Cuts was born wearing glasses. The intended experience is a **live loop**:

```
Ray-Ban Meta glasses  ──image frames──▶  home engine (small VLM + TTS)  ──▶  narration in your ear
                                              │
                                              └──── finished cuts ────▶  the Space (watch · library)
```

You walk through a moment; the narrator speaks it back to you, **chunk by chunk**, in
near-real-time — each line short enough to land while the moment is still *recent past*,
never racing ahead of what just happened. Within a single clip the narrator remembers what
it already said (intra-clip coherence), so the clip reads as one continuous wry little story.

**One pipeline, two surfaces:** the same narration plays *in your ear* live, and lands in the
**Space** below as a finished cut you can re-watch — with film-style subtitles that crawl in
sync with the voice — and publish to a library.

## What's in this Space

The Space is the **view platform + library** half of the loop — a small streaming-channel UI:

- **A live stage** with the current moment and **movie-style subtitles** (short
  phrase-sized lines over a constant dark bar, advancing with the voice-over).
- **Voice-over replay**, with a compact custom player whose video, sound, captions, and progress
  share the same audio clock.
- **A hero library** of real Ray-Ban Meta glasses moments, seeded so the channel is never empty.
- **"Try it"** — a tucked-away sandbox (open only on request) to narrate your *own* short video.

## How it was built

| Piece | Choice | Why |
|---|---|---|
| Narrator (VLM) | `Qwen/Qwen3-VL-8B-Instruct` | Strong grounded captioning at 8B — well under 32B |
| Voice (TTS) | **Kokoro** (24 kHz) | Tiny, expressive, open; one signature deadpan delivery |
| Space runtime | Gradio 6 on CPU, viewer-only for live demo | The judged canvas: public theater + library |
| Real-time engine | FastAPI WS home node, **llama.cpp** | The live in-ear loop + demo video; no cloud LLM/TTS API |
| Capture | iOS app for Ray-Ban Meta glasses (`ios/SmallCuts/`) | First-person moments, the way it's meant to be lived |

Implementation is a cross-model team effort: **Claude (Opus)** orchestrates, **Codex (GPT-5.x)**
implements, with **GLM** review and a **Gemini** eval judge.

## Hackathon compliance

| Rule | How Small Cuts complies |
|---|---|
| Gradio app hosted as a Space under the org | The app **is** the product — this Space |
| Every model < 32B | 8B VLM narrator + small Kokoro TTS, all open weights |
| Demo video | Filmed POV with Ray-Ban Meta glasses → narrated by the app *(link below)* |
| Social post | Linked from this README *(link below)* |
| Track 2 — **Thousand Token Wood** (`track:wood`) | Whimsical, delightful, AI-load-bearing, original |
| Off the Grid (`achievement:offgrid`) | Live inference/TTS runs on local hardware; public Space reads finished cuts only |
| Llama (`achievement:llama`) | The live engine runs through `llama.cpp` |

- 📹 **Demo video:** _TODO — add public link before submission_
- 📣 **Social post:** _TODO — add link before submission_
- 📝 **Field notes:** [hf.co/blog/macayaven/small-cuts-field-notes](https://huggingface.co/blog/macayaven/small-cuts-field-notes)

**Bonus quests claimed:** Off-Brand (`offbrand`, custom cinematic frontend) · Off the Grid
(`offgrid`, local small-model engine for the live loop) · Llama (`llama`, llama.cpp) · Field
Notes (`fieldnotes`, the write-up above).

## Quick start

```bash
# install (CI-equivalent minimal)
uv sync --extra dev

# run the Space/viewer locally with the deterministic mock backend (no model download)
SMALL_CUTS_BACKEND=mock uv run --no-sync python app.py

# run with the real local VLM (downloads weights)
SMALL_CUTS_BACKEND=transformers uv run --no-sync python app.py

# run the real-time engine (needs `brew install llama.cpp`)
SMALL_CUTS_BACKEND=llama_cpp SMALL_CUTS_TTS_BACKEND=kokoro uv run python -m small_cuts.engine

# the gate (mirrors CI exactly)
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

## Repository map

- `app.py` — Hugging Face Space entrypoint (Gradio CPU viewer/library)
- `src/small_cuts/` — the product: `viewer.py` (streaming viewer), `narrator.py` (VLM backends),
  `tts.py` (Kokoro), `styles.py` (grounded prompt), `engine/` (real-time home node), `seed_media/`
- `ios/SmallCuts/` — the Ray-Ban Meta glasses capture app
- `docs/` — [hackathon rules](docs/hackathon-rules.md) · [architecture](docs/product/architecture.md) ·
  [contracts](docs/contracts/) · [progress](docs/progress.md)
- `CLAUDE.md` — operational conventions (the canonical command list lives here)

## Engineering discipline

- `main` is protected (PR-based workflow); CI runs ruff lint + format check, pytest, and a
  gitleaks secret scan on every push/PR.
- **No secrets in the repo, ever.** Secrets live in 1Password Connect (local dev) and HF Space
  secrets (deployment). Client-facing endpoints use Tailnet MagicDNS HTTPS, never raw IPs.
