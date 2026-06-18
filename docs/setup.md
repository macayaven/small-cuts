# Setup

## Run it locally (fastest loop — no model downloads)

```bash
git clone https://github.com/macayaven/small-cuts.git
cd small-cuts
uv sync --extra dev
# deterministic mock narrator + mock TTS; boots in seconds
uv run --no-sync python app.py            # → http://127.0.0.1:7860
```

`--no-sync` keeps the `tts` extra that a bare `uv run` would prune.

## Real models (optional)

```bash
# transformers backend — the shipped narrator, Qwen3-VL-8B (8B, ≤32B):
uv sync --extra dev --extra local --extra tts
SMALL_CUTS_BACKEND=transformers SMALL_CUTS_TTS_BACKEND=kokoro uv run python app.py

# llama.cpp backend — GGUF via the `llama-server` binary (brew install llama.cpp):
SMALL_CUTS_BACKEND=llama_cpp SMALL_CUTS_GGUF_PATH=/path/to/model.gguf \
  SMALL_CUTS_TTS_BACKEND=kokoro uv run python app.py
```

## Local gate (mirrors CI)

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

## Key environment variables

| Variable | Default | Meaning |
|---|---|---|
| `SMALL_CUTS_BACKEND` | `mock` | `mock` \| `transformers` \| `llama_cpp` |
| `SMALL_CUTS_TTS_BACKEND` | `mock` | `mock` \| `kokoro` |
| `SMALL_CUTS_MODEL_ID` | `Qwen/Qwen3-VL-8B-Instruct` | HF model id for the transformers backend |
| `SMALL_CUTS_GGUF_PATH` | — | local GGUF path for the `llama_cpp` backend |
| `SMALL_CUTS_ENGINE_URL` | — | engine mode: poll `GET /v1/scenes` from a home/engine URL |
| `SMALL_CUTS_RELAY_BUCKET` | — | relay mode: read finished scenes from an HF bucket |
| `SMALL_CUTS_ENABLE_UPLOAD_SANDBOX` | — | with a relay bucket, enable the Modal-backed "try it" upload |

The four viewer modes (engine / pure-relay / hybrid-relay+upload / local-upload) are selected from
these at build time — see [`architecture.md`](architecture.md). The hybrid upload path also needs
`SMALL_CUTS_MODAL_API_URL` + `SMALL_CUTS_MODAL_API_TOKEN` (the Modal endpoint + its Bearer token). The
real-time home engine runs with `python -m small_cuts.engine` (see the root [`CLAUDE.md`](../CLAUDE.md)).

## Secrets

**No secrets live in this repo and the core app needs none at runtime.** An HF token (for deploys) and
Modal/Sentry tokens are read from the environment or a secrets store, never committed; `gitleaks` runs
in CI on every push and PR. Set `SENTRY_DSN` as a Space secret to receive startup/upload telemetry
(optional — without it the app still surfaces inline errors).
