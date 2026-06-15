# CLAUDE.md — `src/small_cuts/engine/` (inference / home node)

Module-local notes for the **real-time home-node engine**. Global rules + canonical commands are in
the **root `CLAUDE.md`**; the pipeline design + decisions are in the **KB**
(`10-projects/small-cuts/inference/` and `…/architecture/`). Contract shapes: `docs/contracts/`.

## What's here
- `app.py` — FastAPI factory. `session.py` — WS `/v1/session` runner (D8 coalesce-to-newest, one
  ack per envelope, honest retries). `library.py` — SceneLibrary (sqlite-WAL + media files, in-proc
  pub/sub, SSE replay). `__main__.py` — uvicorn entry.
- Endpoints: WS `/v1/session` · `GET /v1/scenes` · SSE `GET /v1/scenes/stream` (Last-Event-ID) ·
  `PATCH /v1/scenes/{id}` (visibility — the viewer's only write) · `GET /media/{scene}/{file}`.

## Run (needs `uv sync --extra engine`)
```bash
SMALL_CUTS_BACKEND=llama_cpp SMALL_CUTS_TTS_BACKEND=kokoro uv run python -m small_cuts.engine  # :8077
SMALL_CUTS_BACKEND=mock uv run python -m small_cuts.engine                                      # smoke
```
- **Warm it first:** cold first moment ≈ 17 s (llama-server spawn + model load); warm e2e ≈ 5.7–6.9 s
  (≤10 s budget). Send one throwaway moment after start.

## Env
`SMALL_CUTS_ENGINE_HOST`/`_PORT` (127.0.0.1 / 8077; set host explicitly for LAN/Tailnet) ·
`_LIBRARY_DIR` (`~/.small-cuts/library`) ·
`_GGUF_PATH`/`_MMPROJ_PATH` · `_LLAMA_SERVER` (binary) · `_LLAMA_URL` (external server, skips spawn) ·
`_MODEL_ID` · `_TEMPERATURE` (0.3).

## llama.cpp
- `brew install llama.cpp` → `llama-server` on PATH; spawns lazily on first moment. **Keep the
  `--image-max-tokens 1024` floor** (Qwen-VL grounding; portrait glasses frames OOM Metal without it).
- CI uses an in-process fake OpenAI server — no real model needed.

## Inspect a running engine
- Loopback: `http://127.0.0.1:8077/v1/scenes` (JSON) ·
  `curl -N http://127.0.0.1:8077/v1/scenes/stream` (SSE).
- LAN/Tailnet: set `SMALL_CUTS_ENGINE_HOST=0.0.0.0`, then use the host name, e.g.
  `http://mac-studio:8077/v1/scenes`.
- Library files live at `~/.small-cuts/library`. Engine validates every frame against
  `docs/contracts/`.
