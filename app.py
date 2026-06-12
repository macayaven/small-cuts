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

ON_SPACE = bool(os.environ.get("SPACE_ID"))

try:
    import spaces  # noqa: F401  (must precede torch imports for ZeroGPU)
except ImportError:  # local dev / CI: no ZeroGPU
    spaces = None

if ON_SPACE:
    os.environ.setdefault("SMALL_CUTS_BACKEND", "transformers")
    os.environ.setdefault("SMALL_CUTS_TTS_BACKEND", "kokoro")

from small_cuts import narrator  # noqa: E402
from small_cuts.viewer import THEME, build_viewer_app  # noqa: E402

# Eager load: download + pack weights at startup, not on the first click.
# The @spaces.GPU mark lives on the viewer's go-live handler (via ui._gpu;
# ZeroGPU's startup scan only finds GPU functions on what Gradio binds).
_backend = narrator.get_backend()
if spaces is not None and _backend.name == "transformers":
    _backend._load()

# The Space never runs engine mode: SMALL_CUTS_ENGINE_URL is only set on a
# viewer machine next to a home-node engine. Here the viewer builds in
# upload mode, feeding the stage from the local pipeline. No main-process
# TTS pre-warm: kokoro's torch use must stay inside @spaces.GPU workers.
demo = build_viewer_app()

if __name__ == "__main__":
    demo.launch(theme=THEME)
