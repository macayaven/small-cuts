"""Hugging Face Space entrypoint for Small Cuts.

Local dev keeps the lazy/mock defaults; on a Space this module wires the real
backends eagerly so visitors never pay the model-load cost per click:

- ``import spaces`` happens before anything touches torch (ZeroGPU hijack).
- The narrator loads at module scope (ZeroGPU packs the weights at startup).
- The narration hot path runs under ``@spaces.GPU``.
- TTS runs inside @spaces.GPU workers too (kokoro's torch use poisons
  worker forks if it ever runs in the main process).
"""

import os
import sys
import warnings
from pathlib import Path

from starlette.exceptions import StarletteDeprecationWarning

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

warnings.filterwarnings(
    "ignore",
    message=r".*HTTP_422_UNPROCESSABLE_ENTITY.*HTTP_422_UNPROCESSABLE_CONTENT.*",
    category=StarletteDeprecationWarning,
)

ON_SPACE = bool(os.environ.get("SPACE_ID"))
ENGINE_MODE = bool(os.environ.get("SMALL_CUTS_ENGINE_URL", "").strip())

from small_cuts.hf_relay import RELAY_BUCKET_ENV  # noqa: E402

RELAY_MODE = bool(os.environ.get(RELAY_BUCKET_ENV, "").strip())
MODAL_UPLOAD_MODE = bool(os.environ.get("SMALL_CUTS_MODAL_API_URL", "").strip())
VIEWER_ONLY_MODE = ENGINE_MODE or RELAY_MODE or MODAL_UPLOAD_MODE
NEEDS_LOCAL_INFERENCE = not VIEWER_ONLY_MODE

try:
    import spaces  # noqa: F401  (must precede torch imports for ZeroGPU)
except ImportError:  # local dev / CI: no ZeroGPU
    spaces = None

if ON_SPACE and NEEDS_LOCAL_INFERENCE:
    os.environ.setdefault("SMALL_CUTS_BACKEND", "transformers")
    os.environ.setdefault("SMALL_CUTS_TTS_BACKEND", "kokoro")

from small_cuts import narrator  # noqa: E402
from small_cuts.observability import init_sentry  # noqa: E402
from small_cuts.viewer import THEME, build_viewer_app  # noqa: E402

init_sentry()

# Eager load: download + pack weights at startup, not on the first click.
# The @spaces.GPU mark lives on the viewer's go-live handler (via ui._gpu;
# ZeroGPU's startup scan only finds GPU functions on what Gradio binds).
if NEEDS_LOCAL_INFERENCE:
    _backend = narrator.get_backend()
    if spaces is not None and _backend.name == "transformers":
        _backend._load()

# In engine mode the Space is only a public reader for a private home-node engine, so it must not
# warm local model weights or expose upload narration controls. No main-process TTS pre-warm:
# kokoro's torch use must stay inside @spaces.GPU workers.
demo = build_viewer_app()

if __name__ == "__main__":
    demo.launch(theme=THEME)
