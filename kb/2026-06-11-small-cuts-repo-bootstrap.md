---
projectId: small-cuts
id: 2026-06-11-small-cuts-repo-bootstrap
---

# Small Cuts — Repo Bootstrap (2026-06-11)

- **What changed:** `macayaven/small-cuts` went from empty to a working
  skeleton on branch `claude/adoring-clarke-49l3uk`: Gradio vertical slice
  (mock backend end-to-end), pluggable inference backends (mock /
  transformers / llama_cpp), style presets + prompt builder, unit tests,
  CI (ruff lint+format, pytest, gitleaks secret scan), full docs set, KB
  note mirrors.
- **Why:** 4 days to deadline; the judged artifact is a Gradio Space, so the
  fastest path to a strong submission is a disciplined repo whose `app.py`
  deploys to the Space unchanged, with CI guarding quality from commit one.
- **Evidence / commands:** `uv run pytest` (green), `uv run ruff check .`
  (clean), `SMALL_CUTS_BACKEND=mock python app.py` (UI smoke). CI workflow at
  `.github/workflows/ci.yml` runs on push.
- **Current status:** M0 complete. Branch pushed; PR + branch protection are
  Carlos-side actions (no admin API in the bootstrap session).
- **Next action:** M1 — model eval on DGX/Mac (3 candidate VLMs × fixed photo
  set), pick narrator model, tune prompts.
- **Risks:** narration specificity of small VLMs unvalidated; ZeroGPU latency;
  submission mechanics unverified; canonical KB not yet updated (this note is
  a mirror pending import).
