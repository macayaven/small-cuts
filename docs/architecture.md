# Small Cuts — Architecture

## Principle

**The Space is the product.** Everything a judge touches runs inside the
Hugging Face Space. All other machines (Mac Studio, DGX Spark, phones, glasses)
are development, evaluation, and content-capture tools.

```
┌─────────────────────────── Hugging Face Space (judged artifact) ──────────────────────────┐
│                                                                                           │
│  Gradio UI (custom cinematic theme — "Off-Brand")                                         │
│   │  image / clip frame / webcam            ┌──────────────────────────────┐              │
│   ▼                                         │ styles.py                    │              │
│  ui.py ──────► narrator.py ◄────────────────│ director presets +           │              │
│                   │                         │ prompt builder               │              │
│                   ▼                         └──────────────────────────────┘              │
│            Backend (pluggable, env SMALL_CUTS_BACKEND)                                    │
│              ├─ mock          deterministic, CI/tests, no weights                         │
│              ├─ transformers  small VLM on ZeroGPU (e.g. SmolVLM2 / Qwen-VL ≤8B)          │
│              └─ llama_cpp     GGUF via llama.cpp (CPU fallback + "Llama Champion")        │
│                   │                                                                       │
│                   ▼                                                                       │
│            TTS (small, local — M2) ──► audio + title card ──► shareable output            │
└───────────────────────────────────────────────────────────────────────────────────────────┘

  Capture sources (feed the demo & the UI, never load-bearing):
   • Ray-Ban Meta glasses → footage exported via phone → demo video + sample inputs
   • iPhone 14 Pro / Redmi Note 14 Pro+ → mobile browser upload (Gradio is responsive)
   • Webcam tab in the UI

  Live Mode (confirmed direction; continuous mode is stretch M3.5):
   • Audio out: phone browser plays the Space's TTS → Bluetooth → glasses speakers (free)
   • Continuous: phone camera → Gradio streaming → scene-change gate → narrate → TTS stream
   • Glasses-camera capture via Meta Wearables DAT: post-hackathon, unverified

  Dev/eval machinery (not judged):
   • Mac Studio M4 Max  → orchestration, dev, video editing
   • DGX Spark 128GB    → candidate-model evaluation harness, optional LoRA fine-tune
                          ("Well-Tuned" quest), batch frame preprocessing experiments
   • 1Password Connect  → local dev secrets; HF Space secrets for deployment
   • Tailnet            → access between Carlos's machines only
```

## Key decisions (and why)

| Decision | Choice | Rationale |
|---|---|---|
| Demo surface | Gradio Space (only) | Hackathon hard rule; judges must run it |
| Glasses role | Capture for demo video + sample content | Removes pairing fragility; preserves wow |
| Most reliable capture path | Any phone browser → upload | No native app needed in 4 days |
| Inference location | Inside the Space (ZeroGPU + CPU fallback) | "Off the Grid" quest; no cloud APIs |
| DGX Spark role | Model eval + optional fine-tune | Can't serve judges; perfect for picking the best ≤8B narrator and for "Well-Tuned" |
| Mac Studio role | Dev + demo video production | — |
| Backend abstraction | `SMALL_CUTS_BACKEND` env, 3 implementations | CI runs without GPU; llama.cpp path is a quest multiplier; model swap is one env var |
| Model candidates (M1 eval) | SmolVLM2-2.2B-Instruct · Qwen2.5-VL-3B/7B-Instruct · gemma-3-4b-it | All ≤8B, vision-capable, open weights; final pick by narration quality on a fixed eval set (unverified until run) |
| TTS candidates (M2) | Kokoro-82M · other ≤1B open TTS | Tiny, fast, runs CPU-side |

## Secrets

No runtime secrets are required for the core app (local models only). HF token
for deployment lives in 1Password Connect locally and in GitHub Actions / Space
secrets remotely. `gitleaks` runs in CI on every push.

## Verification commands

```bash
uv run pytest                          # unit tests (mock backend)
uv run ruff check . && uv run ruff format --check .
SMALL_CUTS_BACKEND=mock uv run python app.py        # UI smoke test
SMALL_CUTS_BACKEND=transformers uv run python app.py  # real model (M1+)
```
