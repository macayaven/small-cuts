# Implementation Plan (deadline: June 15, 2026)

## M0 — Bootstrap ✅ (June 11, this session)

- Repo scaffolding, CI (ruff + pytest + gitleaks), docs, KB notes.
- Vertical slice: Gradio app runs end-to-end with the **mock backend**
  (image → director style → deterministic narration → title card).
- Pluggable backend interface with `transformers` and `llama_cpp` stubs wired.

## M1 — Real narration (June 12)

- Eval harness ✅ (`src/small_cuts/eval.py`): fixed set of ~12 personal photos ×
  candidate VLMs (SmolVLM2-2.2B, Qwen2.5-VL-3B/7B, gemma-3-4b-it) × 3 styles.
  **Run on DGX Spark** (CUDA — results transfer to ZeroGPU; 128GB fits all
  candidates without juggling):
  ```bash
  git clone https://github.com/macayaven/small-cuts && cd small-cuts
  uv sync --extra local
  uv run python -m small_cuts.eval --images ~/eval-photos --out eval-report.md
  ```
  Score the report for specificity/groundedness/voice (rubric included).
- Pick the model; tune the system prompt + per-style few-shots.
- Acceptance: 8/12 eval images produce narration a human laughs or nods at,
  zero hallucinated objects in 10/12.

## M2 — Performance layer (June 13)

- TTS (Kokoro-82M first candidate) behind the same backend pattern.
- Title-card renderer (PIL) + custom Gradio theme/CSS → **Off-Brand** quest.
- Streaming text reveal in UI.

## M3 — Space live (June 13–14)

- Create `build-small-hackathon/small-cuts` Space; ZeroGPU + CPU fallback.
- Decide llama.cpp path (Llama Champion) based on VLM GGUF stability.
- Load test: 3 concurrent narrations; cold-start measurement.

## M3.5 — Continuous Live Mode (stretch, only if M0–M3 green)

- Phone camera → Gradio streaming → scene-change gate → narration → streamed TTS
  → played through Ray-Ban Metas via Bluetooth (audio path itself is free once
  M2 TTS exists — use it in the demo video regardless).

## M4 — Submission assets (June 14)

- Film POV footage with Ray-Ban Metas; cut ≤90s demo video on Mac Studio.
- Social post draft; Field Notes blog post draft (→ **Field Notes** quest).
- Stretch only if green: clip input, day-reel, LoRA fine-tune (**Well-Tuned**).

## M5 — Submit (June 15, morning — do not use the deadline day as buffer-free)

- Final smoke test from both phones; submit Space + video + post.
- Verify quest claiming mechanism and apply tags/metadata.
