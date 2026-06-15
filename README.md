---
title: Small Cuts
emoji: 🎬
colorFrom: indigo
colorTo: purple
sdk: gradio
sdk_version: 6.18.0
app_file: app.py
hf_oauth: true
pinned: true
license: mit
short_description: A deadpan narrator for your life, from small open models.
models:
  - Qwen/Qwen3-VL-8B-Instruct
tags:
  - track:wood
  - sponsor:modal
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
model watches your moment and a small text-to-speech voice speaks the line, the way a film
narrator would if your life were the film.

There is exactly **one narrator**: a single deadpan, unnamed voice. No menus, no director to
pick. You point at what's happening; it tells you what it means.

This is a submission to the **Build Small Hackathon** ("Small Models, Big Adventures" —
Gradio × Hugging Face).

---

## Two paths, one finished cut

Small Cuts is a deliberate comparison of two techniques that both land as the **same** finished
artifact in this Space — a clip with a generated title, narration, Kokoro voice, synced
captions, a library tile, and a source badge.

| Path | Who | Channel | What it proves | Badge |
|---|---|---|---|---|
| **Whole video, one pass** | A judge, in this Space | Past events, any recording | It is **real and running** — verify it yourself, no access to the maker's hardware needed | `source="upload"` |
| **Pieces + hints** | The wearer (Ray-Ban Meta glasses / iOS) | Clips from ~3s ago | The **soul** — embodied, off-grid, narrated in-ear *while the moment is still recent past* | `source="glasses"` |

The public Space never reaches the maker's local hardware; the private home engine never exposes
inference hardware to the public. Same output shape, two very different journeys.

---

## How judges can try it

The Space is the **view platform + library** half of the loop:

- **A live stage** with the current moment and movie-style subtitles over a constant dark bar,
  advancing with the voice-over.
- **Voice-over replay** in a compact custom player whose video, sound, captions, and progress all
  share one audio clock.
- **A public library** of real Ray-Ban Meta glasses moments, generated through the same local
  engine path so the channel is never empty. Source clips and mark points are curated; the visible
  titles, narration, voice, thumbnails, and clips are **produced by Small Cuts**.
- **"Try it"** — a tucked-away, HF-login upload drawer. Sign in, drop a short video, and a private
  **Modal** GPU service runs the real Qwen + Kokoro pipeline and replays your generated cut in the
  same theater. This is the judge-verifiable path: no glasses or iOS required.

---

## Architecture in one glance

```
Ray-Ban Meta glasses ──image frames──▶  home engine (small VLM + TTS)  ──▶  narration in your ear
                                              │
                                              └──── finished cuts ────▶  the Space (watch · library)

judge's browser ──short video──▶  Modal GPU (Qwen3-VL-8B + Kokoro)  ──▶  finished cut in the Space
```

You walk through a moment, tap **Action!**, then tap **Cut!** when the scene has a readable beat.
The narrator watches a selected first-person frame and speaks one grounded, deadpan line back in
your ear while the moment is still recent past. The finished cut lands in the Space as a short POV
clip with synced captions, title, voice, and library thumbnail.

---

## How it was built

| Piece | Choice | Why |
|---|---|---|
| Narrator (VLM) | `Qwen/Qwen3-VL-8B-Instruct` | Strong grounded captioning at **8B — well under 32B** |
| Voice (TTS) | **Kokoro** (24 kHz) | Tiny, expressive, open; one signature deadpan delivery |
| Space runtime | Gradio 6 on CPU | Public theater + library; uploads call Modal instead of warming models |
| Judge upload service | **Modal** GPU app (`small-cuts-postcut`) | Finished-video verification path with real Qwen + Kokoro output |
| Local live engine | FastAPI WS home node, **llama.cpp** | The in-ear loop + demo video; no cloud LLM/TTS API |
| Capture | iOS app for Ray-Ban Meta glasses (`ios/SmallCuts/`) | First-person moments, the way it's meant to be lived |

Built by **Carlos Crespo Macaya** as architect and lead. Development was accelerated with an
AI toolchain — Claude (Opus) for design critique, Codex (GPT-5.x) for paired implementation,
GLM for review, and Gemini for eval — all directed by Carlos.

---

## ≤32B compliance

Every model is small and open-weight:

- **Narrator:** `Qwen/Qwen3-VL-8B-Instruct` — **8B parameters**, comfortably under the 32B cap.
- **Voice:** **Kokoro** — a tiny open TTS model.

There is no cloud LLM anywhere in the loop. The live, in-ear path runs entirely on local hardware
through **llama.cpp**; the judge upload path runs the same small models on a Modal GPU so reviewers
can verify real output without touching the maker's machine.

---

## Hackathon compliance

| Rule | How Small Cuts complies |
|---|---|
| Gradio app hosted as a Space under the org | Final submission promotes to `build-small-hackathon/small-cuts` after personal-profile staging passes |
| Every model < 32B | 8B VLM narrator + small Kokoro TTS, all open weights |
| Demo video | Filmed POV with Ray-Ban Meta glasses → narrated by the app *(link below)* |
| Social post | Linked from this README *(link below)* |
| Track 2 — **Thousand Token Wood** (`track:wood`) | Whimsical, delightful, AI-load-bearing, original |
| Best Use of Modal (`sponsor:modal`) | The judge upload path runs Qwen + Kokoro on a Modal GPU |
| Off the Grid (`achievement:offgrid`) | Live inference/TTS run on local hardware; the public Space reads finished cuts only |
| Off-Brand (`achievement:offbrand`) | Custom cinematic frontend past the stock Gradio look |
| Llama (`achievement:llama`) | The live engine runs through `llama.cpp` |
| Field Notes (`achievement:fieldnotes`) | Public write-up — [field notes on the HF blog](https://huggingface.co/blog/build-small-hackathon/small-cuts-field-notes) |

### Submission links

- 📹 **Demo video (YouTube):** _TODO — add public link before submission_
- 📣 **Social post (Reddit):** _TODO — add link before submission_
- 📣 **Social post (LinkedIn):** _TODO — add link before submission_
- 📝 **Field notes / write-up:** [hf.co/blog/build-small-hackathon/small-cuts-field-notes](https://huggingface.co/blog/build-small-hackathon/small-cuts-field-notes)

> **Integrity note:** every preselected/hero clip in this Space is narrated by the **actual
> Small Cuts pipeline** (real Qwen3-VL-8B + Kokoro output) — never hand-written narration.

---

## License

Released under the **MIT License** — see [`LICENSE`](LICENSE) in the repository.
