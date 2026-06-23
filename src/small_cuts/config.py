"""Single source of truth for configuration that crosses the Space↔Modal boundary.

Defined here once and imported by both the Gradio Space (the ``small_cuts`` package) and the
Modal ``/v2/narrate`` app (``modal_app/midcuts_narrate.py``), so the two sides can never disagree
on an upload cap or an env-var key — the exact drift that let the UI accept 160 MB while Modal
rejected at 30 MB. Component-local tuning (per-process timeouts, viewer UI limits, persona/language
data, the frozen v1 ``small_cuts_postcut`` app) deliberately stays where it is used.

Pure constants only: this module imports nothing from the package, so it stays importable from
inside the minimal Modal container image (which only guarantees ``small_cuts`` + pillow-heif on the
path). Keep it that way.
"""

from __future__ import annotations

# ── Upload limits — enforced identically by the Space front-door and Modal /v2/narrate ──
MAX_UPLOAD_BYTES = 160 * 1024 * 1024  # 160 MB
MAX_UPLOAD_SECONDS = 120.0

# ── Env-var NAMES on the Space↔Modal wire (keys only — never secret values) ──
MODAL_API_TOKEN_ENV = "SMALL_CUTS_MODAL_API_TOKEN"  # Bearer the Space sends and Modal validates
RELAY_WRITE_TOKEN_ENV = "SMALL_CUTS_RELAY_WRITE_TOKEN"  # Modal's scoped bucket-write token
RELAY_BUCKET_ENV = "SMALL_CUTS_RELAY_BUCKET"  # relay bucket id the Space reads
RELAY_HOOK_URL_ENV = "SMALL_CUTS_RELAY_HOOK_URL"  # Space hook URL Modal POSTs after a publish
RELAY_HOOK_TOKEN_ENV = "SMALL_CUTS_RELAY_HOOK_TOKEN"  # Bearer shared by the push hook

# ── Relay object layout (Modal writes finished scenes under this prefix; the Space reads it) ──
DEFAULT_RELAY_PREFIX = "relay"
