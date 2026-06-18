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
| **Pieces + hints** | The wearer (Ray-Ban Meta glasses / iOS) | A short `Action!`→`Cut!` take | The **soul** — embodied, off-grid; ~6s after `Cut!` (warm) a deadpan line is spoken **in-ear** *(recent past, not real-time)* | `source="glasses"` |

The public Space never reaches the maker's local hardware; the private home engine never exposes
inference hardware to the public. Same output shape, two very different journeys.

---

## How judges can try it

The Space is the **view platform + library** half of the loop:

- **A live stage** with the current moment and movie-style subtitles over a constant dark bar,
  advancing with the voice-over.
- **Voice-over replay** in a compact custom player whose video, sound, captions, and progress all
  share one audio clock.
- **A public library** of curated real Ray-Ban Meta glasses moments, so the channel is never empty —
  real POV clips with the real **Kokoro** voice, hand-curated into a seed library (not regenerated at
  runtime).
- **"Try it"** — a tucked-away upload drawer. Drop a short video and, while the shared demo budget
  still has capacity, a private **Modal** GPU service can run the real Qwen + Kokoro pipeline and
  replay the generated cut in the same theater. Local prototypes can use the mock narrator/TTS
  path. Successful uploads are stored in a persistent demo library and remain available after
  refresh.

---

## Architecture in one glance

```
Ray-Ban Meta glasses ──image frames──▶  home engine (small VLM + TTS)  ──▶  narration in your ear
                                              │
                                              └──── finished cuts ────▶  the Space (watch · library)

judge's browser ──short video──▶  Modal GPU (Qwen3-VL-8B + Kokoro)  ──▶  finished cut in the Space
```

You walk through a moment, tap **Action!**, then tap **Cut!** when the scene has a readable beat.
The narrator watches a selected first-person frame and, **~6 seconds later** (warm; ~17s on a cold
engine), speaks one grounded, deadpan line back in your ear — fast enough to land as *recent past*,
not real-time. The finished cut lands in the Space as a short POV clip with synced captions, title,
voice, and library thumbnail. *(Rolling in-ear narration **during** the moment is a planned
fast-follow — at the current model's speed one moment yields ~35–44s of audio per ~3s of video, so
the spoken line is one complete clip after `Cut!`, not a live stream.)*

## Local prototype run

This prototype removes sign-in from uploads. Local testing uses mock narration and mock TTS so the
app starts quickly:

```bash
SMALL_CUTS_BACKEND=mock \
SMALL_CUTS_TTS_BACKEND=mock \
SMALL_CUTS_DISABLE_ENGINE_AUTODETECT=1 \
SMALL_CUTS_BUCKET_MOUNT_PATH="$HOME/.small-cuts/prototype-bucket" \
SMALL_CUTS_RELAY_DIRECT_MEDIA_URLS=1 \
SMALL_CUTS_DAILY_GPU_BUDGET_SECONDS=1200 \
SMALL_CUTS_GPU_SECONDS_PER_UPLOAD_RESERVATION=60 \
SMALL_CUTS_UPLOAD_RESERVATION_TTL_SECONDS=1800 \
uv run --extra dev python app.py
```

Upload abuse prevention is intentionally identity-free in this prototype. The app reserves a small
chunk of the shared daily processing budget before generation starts, then charges the actual
processing wall time when the job finishes. When the committed budget reaches
`SMALL_CUTS_DAILY_GPU_BUDGET_SECONDS`, uploads are paused until the next UTC day. The current
persistence backend is local SQLite plus filesystem media; the same viewer boundary can later be
backed by Cloud Storage plus Firestore for hosted deployment.
If a browser or Space restart abandons a preflight reservation before Modal starts, the reservation
is released after `SMALL_CUTS_UPLOAD_RESERVATION_TTL_SECONDS` so a failed handoff does not consume
the shared daily budget for the rest of the day.

Set `SENTRY_DSN` as a Space secret to receive startup, polling, and upload-processing failures in
Sentry. Without that secret, the app still shows inline upload errors but does not send telemetry.

For public HF relay buckets, set `SMALL_CUTS_RELAY_DIRECT_MEDIA_URLS=1` so gallery videos resolve
through Hugging Face's bucket CDN/range endpoint instead of being served through the Space's mounted
filesystem path. Keep it unset for private buckets that should not be browser-readable.

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

- 📝 **Field notes / write-up:** [hf.co/blog/build-small-hackathon/small-cuts-field-notes](https://huggingface.co/blog/build-small-hackathon/small-cuts-field-notes)

> **Note on the demo library:** the **"try it"** upload path runs the real Small Cuts pipeline live
> — Qwen3-VL-8B narration + Kokoro voice on a Modal GPU. The preselected hero clips use the real
> Kokoro voice and the same finished-cut shape, curated into a seed library so the channel is never
> empty.

---

## License

Released under the **MIT License** — see [`LICENSE`](LICENSE) in the repository.
