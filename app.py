"""Hugging Face Space entrypoint for Small Cuts.

Local dev keeps the lazy/mock defaults; on a Space this module wires the real
backends eagerly so visitors never pay the model-load cost per click:

- ``import spaces`` happens before anything touches torch (ZeroGPU hijack).
- The narrator loads at module scope (ZeroGPU packs the weights at startup).
- The narration hot path runs under ``@spaces.GPU``.
- Kokoro TTS pre-warms on CPU at startup.
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

from small_cuts import narrator, tts  # noqa: E402
from small_cuts.ui import THEME, build_app  # noqa: E402

# Eager load: download + pack weights at startup, not on the first click.
# The @spaces.GPU mark lives on the ui.py event handlers (ZeroGPU's startup
# scan only finds GPU functions on what Gradio binds).
_backend = narrator.get_backend()
if spaces is not None and _backend.name == "transformers":
    _backend._load()

if ON_SPACE and os.environ.get("SMALL_CUTS_TTS_BACKEND") == "kokoro":
    try:  # pre-warm the CPU TTS pipeline; first click stays snappy
        tts.speak("Roll sound.", backend=tts.get_tts_backend())
    except Exception as exc:  # TTS is a bonus track — never block the narrator
        print(f"[small-cuts] kokoro pre-warm failed, falling back to mock TTS: {exc}")
        os.environ["SMALL_CUTS_TTS_BACKEND"] = "mock"

demo = build_app()

if __name__ == "__main__":
    demo.launch(theme=THEME)
