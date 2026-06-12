# Spec: LlamaCppBackend via llama-server (M3, issue #14 → achievement:llama)

## Purpose

Make `SMALL_CUTS_BACKEND=llama_cpp` real: the narrator runs through the
llama.cpp runtime (Llama Champion badge). Verified end-to-end on 2026-06-12
(see #14 comment): official `Qwen/Qwen3-VL-8B-Instruct-GGUF` Q4_K_M + mmproj
through llama.cpp b9590 produces grounded, on-voice narrations.

Design: a managed **`llama-server` subprocess** spoken to over its
OpenAI-compatible HTTP API — NOT llama-cpp-python chat handlers (the Python
wrapper lags upstream on new vision archs; the server tracks llama.cpp).

## Contract (`src/small_cuts/narrator.py`, replace the stub)

`LlamaCppBackend` keeps `name = "llama_cpp"` and the `Backend` protocol.

### Configuration (env)

- `SMALL_CUTS_LLAMA_URL` — if set (e.g. `http://127.0.0.1:8080`), use this
  already-running llama-server and manage NO subprocess. This is the CI/test
  seam and the local-dev path (`brew install llama.cpp; llama-server …`).
- `SMALL_CUTS_LLAMA_SERVER` — path to a `llama-server` binary; default:
  `shutil.which("llama-server")`. If neither URL nor binary is available,
  `generate` raises `RuntimeError` with an actionable message (mention brew
  and SMALL_CUTS_LLAMA_URL). Do NOT auto-download binaries in this package.
- `SMALL_CUTS_GGUF_PATH` / `SMALL_CUTS_MMPROJ_PATH` — local GGUF paths; if
  unset, resolve via `huggingface_hub.hf_hub_download` from
  `Qwen/Qwen3-VL-8B-Instruct-GGUF` (`Qwen3VL-8B-Instruct-Q4_K_M.gguf`,
  `mmproj-Qwen3VL-8B-Instruct-F16.gguf`). `model_id` reports the repo id or
  the basename of the local GGUF.

### Subprocess management (only when no SMALL_CUTS_LLAMA_URL)

- Lazily started on first `generate` (constructing the backend must not
  spawn anything — mirrors the lazy `_load` pattern).
- Launch: `llama-server -m <gguf> --mmproj <mmproj> --port <free port>
  -c 8192 --image-max-tokens 1024 --host 127.0.0.1`.
  The image-token floor matters: llama.cpp warns Qwen-VL needs ≥ 1024 image
  tokens for grounding accuracy. Keep exactly 1024.
- Wait for readiness by polling `GET /health` (llama-server exposes it)
  with a deadline (~120 s — model load takes a while); kill + RuntimeError
  on timeout. Register `atexit` cleanup that terminates the child.

### Request path

- Reuse `build_messages(style_key, scene_hint)`; system message as-is; user
  content = `[{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,…"}},
  {"type": "text", "text": <user text>}]` (OpenAI vision shape llama-server accepts).
- **Downscale before encoding**: new pure helper in narrator.py
  `def _downscale(image: Image.Image, max_side: int = 1024) -> Image.Image`
  — proportional thumbnail when the longest side exceeds `max_side`
  (full-res portrait glasses frames blow up vision compute; see #14).
  JPEG quality 90.
- Body: `temperature` from `SMALL_CUTS_TEMPERATURE` (default 0.3),
  `max_tokens: 160`. Parse `choices[0].message.content`, return `.strip()`.
- Use `httpx` (already a Gradio dependency) with a generous timeout (120 s).
- Connection/HTTP errors → `RuntimeError` mentioning the server URL.

## Out of scope

- NO ui.py changes (P1 rewrites the UI; backend selection stays env-based).
- NO binary auto-download; NO Space wiring (separate deploy step).

## Verification

`tests/test_llama_backend.py` (committed alongside, uses a fake in-process
HTTP server — no llama binary in CI) must pass, plus the full gate:
`uv run pytest && uv run ruff check && uv run ruff format --check`.
Do not modify tests or spec; if a test looks wrong, stop and explain.
Manual (not CI): with a local `llama-server` running,
`SMALL_CUTS_LLAMA_URL=http://127.0.0.1:8080 SMALL_CUTS_BACKEND=llama_cpp uv run python -c "…narrate(Image.open(...))…"`.
