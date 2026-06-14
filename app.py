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
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

ON_SPACE = bool(os.environ.get("SPACE_ID"))
ENGINE_MODE = bool(os.environ.get("SMALL_CUTS_ENGINE_URL", "").strip())

try:
    import spaces  # noqa: F401  (must precede torch imports for ZeroGPU)
except ImportError:  # local dev / CI: no ZeroGPU
    spaces = None

if ON_SPACE and not ENGINE_MODE:
    os.environ.setdefault("SMALL_CUTS_BACKEND", "transformers")
    os.environ.setdefault("SMALL_CUTS_TTS_BACKEND", "kokoro")

from small_cuts import narrator  # noqa: E402
from small_cuts.viewer import THEME, build_viewer_app  # noqa: E402

# Eager load: download + pack weights at startup, not on the first click.
# The @spaces.GPU mark lives on the viewer's go-live handler (via ui._gpu;
# ZeroGPU's startup scan only finds GPU functions on what Gradio binds).
if not ENGINE_MODE:
    _backend = narrator.get_backend()
    if spaces is not None and _backend.name == "transformers":
        _backend._load()

# In engine mode the Space is only a public reader for a private home-node engine, so it must not
# warm local model weights or expose upload narration controls. No main-process TTS pre-warm:
# kokoro's torch use must stay inside @spaces.GPU workers.
demo = build_viewer_app()

if __name__ == "__main__":
    demo.launch(theme=THEME)
