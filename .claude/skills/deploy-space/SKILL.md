---
name: deploy-space
description: Deploy the Small Cuts app to the Hugging Face Space (build-small-hackathon/small-cuts) and smoke-test it. Use when shipping a new build to the Space.
disable-model-invocation: true
---

# Deploy Small Cuts to the HF Space

Ship the current build to `build-small-hackathon/small-cuts` and verify it. The Space is the judged
artifact — never push red.

## 1. Green gate first (must mirror CI)
```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```
Stop if anything fails.

## 2. Auth
`hf auth whoami` must show a write-scoped login. If not, ask the user to run `! hf auth login`.
(For exact `hf` CLI syntax, use the `huggingface-skills:hf-cli` skill.)

## 3. Upload what the Space needs
`app.py`, `src/` (including `src/small_cuts/seed_media/` — the seed clips are static files served via
`gr.set_static_paths`), `requirements.txt`, and the Space `README.md` (its frontmatter carries the
`track:` / `achievement:` / `sponsor:` tags). Either:
```bash
hf upload --repo-type space build-small-hackathon/small-cuts . . \
  --include "app.py" --include "requirements.txt" --include "README.md" --include "src/**"
```
or push to the Space's git remote.

## 4. Space variables (backends)
```bash
hf spaces variables build-small-hackathon/small-cuts        # list current
# real models on the Space: SMALL_CUTS_BACKEND=transformers  SMALL_CUTS_TTS_BACKEND=kokoro
```

## 5. Smoke test (the fork-poison detector)
After the Space restarts, run a `gradio_client` smoke: **narrate → TTS → narrate-again** — the third
call is what catches kokoro fork-poisoning. Tail logs:
```bash
hf spaces logs build-small-hackathon/small-cuts --tail
```

## Reminders
- ZeroGPU: `@spaces.GPU` marks must be on the handlers Gradio binds; no torch in the main process
  (see `src/small_cuts/CLAUDE.md`).
- Confirm `seed_media/*.mp4` actually shipped — the hero library is empty without them.
