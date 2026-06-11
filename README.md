# Small Cuts 🎬

> *"And that was the moment Carlos realized the coffee had been decaf all along."*

**Small Cuts** turns moments of your life into cinematic narration — an omniscient,
slightly-too-honest narrator in the spirit of *The Invention of Lying*, powered
entirely by **small open models (≤32B)** running inside a Hugging Face Space.

Point it at a photo or a short clip of what's happening around you (from your
phone, webcam, or Ray-Ban Meta glasses footage), pick a director, and Small Cuts
writes — and speaks — the narration of your scene as if your life were a film
and someone wonderful (or merciless) were narrating it.

This is the **challenger submission** for the
[Build Small Hackathon](https://huggingface.co/build-small-hackathon)
(Gradio × Hugging Face, submissions close **June 15, 2026**), built in parallel
to the original *Director's Cut* project. It is rule-shaped from day one:

| Hackathon rule | How Small Cuts complies |
|---|---|
| Gradio app hosted as a Space under the org | The app **is** the product — no companion app required |
| Models ≤ 32B total parameters | Small VLM narrator + small TTS, all open weights |
| Demo video + social post | Filmed POV with Ray-Ban Meta glasses → narrated by the app |
| Track 2 — Thousand Token Wood | Delightful, AI-load-bearing, original |

Targeted bonus quests: **Off the Grid** (no cloud APIs), **Llama Champion**
(llama.cpp runtime), **Off-Brand** (custom cinematic frontend), **Field Notes**
(blog post), and **Well-Tuned** (published narrator-style fine-tune, stretch).

## Quick start

```bash
# install (uv recommended)
uv sync --extra dev

# run the app with the deterministic mock backend (no model download)
SMALL_CUTS_BACKEND=mock uv run python app.py

# run with a real local VLM (downloads weights)
SMALL_CUTS_BACKEND=transformers uv run python app.py

# tests + lint
uv run pytest
uv run ruff check .
```

## Repository map

- `app.py` — Hugging Face Space entrypoint (Gradio)
- `src/small_cuts/` — narrator pipeline: style presets, prompt builder, pluggable model backends
- `tests/` — unit tests (run in CI with the mock backend, no GPU needed)
- `docs/` — [hackathon rules](docs/hackathon-rules.md) · [product strategy](docs/product-strategy.md) · [architecture](docs/architecture.md) · [setup](docs/setup.md) · [implementation plan](docs/implementation-plan.md) · [progress](docs/progress.md) · [demo readiness](docs/demo-readiness.md)
- `kb/` — knowledge-base notes (mirrors of the canonical `.knowledge/` KB on Mac Studio; see `kb/README.md`)

## Engineering discipline

- `main` is protected (PR-based workflow; see `docs/setup.md` for the required
  branch-protection settings — they must be enabled once by an admin).
- CI on every push/PR: ruff lint + format check, pytest, gitleaks secret scan.
- No secrets in the repo, ever. Secrets live in 1Password Connect (local dev)
  and HF Space secrets (deployment).

## Status

Bootstrap phase — see [docs/progress.md](docs/progress.md) for the live tracker.
