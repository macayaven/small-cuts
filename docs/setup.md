# Setup Guide

## Local development

```bash
git clone https://github.com/macayaven/small-cuts.git
cd small-cuts
uv sync --extra dev          # or: pip install -e ".[dev]"

# fastest loop — deterministic mock backend, no model downloads
SMALL_CUTS_BACKEND=mock uv run python app.py
```

Real-model backends (M1+):

```bash
uv sync --extra local        # transformers + torch
SMALL_CUTS_BACKEND=transformers SMALL_CUTS_MODEL_ID=HuggingFaceTB/SmolVLM2-2.2B-Instruct \
  uv run python app.py

uv sync --extra llama        # llama-cpp-python
SMALL_CUTS_BACKEND=llama_cpp SMALL_CUTS_GGUF_PATH=/path/to/model.gguf \
  uv run python app.py
```

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `SMALL_CUTS_BACKEND` | `mock` | `mock` \| `transformers` \| `llama_cpp` |
| `SMALL_CUTS_MODEL_ID` | `HuggingFaceTB/SmolVLM2-2.2B-Instruct` | HF model id for the transformers backend |
| `SMALL_CUTS_GGUF_PATH` | — | local GGUF path for the llama.cpp backend |

## Secrets

There are **no secrets in this repo** and the core app needs none at runtime.

- Local dev: fetch tokens (HF write token for Space deploys) from **1Password
  Connect** — never paste them into files or shell history that gets committed.
- CI: `GITHUB_TOKEN` only (provided by Actions).
- Space: set `HF_TOKEN`-class secrets in the Space settings UI if ever needed.
- `gitleaks` runs in CI on every push and PR.

## Branch protection (one-time admin step — ⚠️ pending)

GitHub MCP tooling in the bootstrap session could not set branch protection.
Carlos (or any session with `gh` + admin) must run once:

```bash
gh api -X PUT repos/macayaven/small-cuts/branches/main/protection \
  -F required_status_checks[strict]=true \
  -F 'required_status_checks[contexts][]=ci' \
  -F enforce_admins=true \
  -F required_pull_request_reviews[required_approving_review_count]=0 \
  -F restrictions=null
```

(Zero required approvals keeps the PR-based workflow without blocking a
solo builder on a 4-day deadline.)

## Tailnet access from cloud Claude Code sessions

Cloud session containers are not on the tailnet by default. `scripts/tailnet-connect.sh`
fixes that: it installs Tailscale (userspace networking — no TUN in these
containers), authenticates with `TS_AUTHKEY`, and writes an SSH config so
`ssh spark` / `ssh mac-studio` dial through `tailscale nc`.

One-time setup by Carlos:

1. Tailscale admin console → **Settings → Keys → Generate auth key** with
   **Reusable + Ephemeral + Pre-approved** (ephemeral nodes vanish when the
   container dies), ideally tagged (e.g. `tag:claude-session`) with ACLs
   limiting it to SSH toward `spark-caeb` and `mac-studio`.
2. Add it as `TS_AUTHKEY` in the Claude Code **environment settings**
   (code.claude.com → environment → secrets/env vars) — never in the repo.
3. Recommended: enable **Tailscale SSH** on both machines
   (`sudo tailscale set --ssh`) with a matching ACL `ssh` rule, so sessions
   need no SSH keypair management at all.
4. Optional, to auto-connect every session: add a `SessionStart` hook to
   `.claude/settings.json` running `bash scripts/tailnet-connect.sh || true`.

Each session then runs (or the hook runs): `bash scripts/tailnet-connect.sh`.

## Deploying the Space (M3)

1. Create the Space **under the hackathon org**: `build-small-hackathon/small-cuts`
   (Gradio SDK, ZeroGPU hardware if available, CPU fallback otherwise).
2. Push this repo's `app.py`, `src/`, `requirements.txt` to the Space
   (`gradio deploy` or a `git push` to the Space remote).
3. Set `SMALL_CUTS_BACKEND=transformers` (ZeroGPU) or `llama_cpp` (CPU) in
   Space variables.
4. Smoke-test from a phone browser — that is the judge experience.
