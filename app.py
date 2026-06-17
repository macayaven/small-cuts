"""Hugging Face Space entrypoint for Small Cuts.

Local dev keeps the lazy/mock defaults. On a Space this module refuses unsafe
CPU local inference and never lets startup failures crash-loop the container:

- ``import spaces`` happens before anything touches torch (ZeroGPU hijack).
- The narrator loads lazily inside the ``@spaces.GPU`` event handler.
- TTS runs inside @spaces.GPU workers too (kokoro's torch use poisons
  worker forks if it ever runs in the main process).
"""

import os
import sys
import warnings
from pathlib import Path

from starlette.exceptions import StarletteDeprecationWarning

ON_SPACE = bool(os.environ.get("SPACE_ID"))
if ON_SPACE:
    # HF Spaces defaults Gradio SSR on; its Node proxy shadows custom FastAPI SSE routes.
    os.environ["GRADIO_SSR_MODE"] = "False"

import gradio as gr  # noqa: E402

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

warnings.filterwarnings(
    "ignore",
    message=r".*HTTP_422_UNPROCESSABLE_ENTITY.*HTTP_422_UNPROCESSABLE_CONTENT.*",
    category=StarletteDeprecationWarning,
)

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

from small_cuts.observability import capture_exception, init_sentry  # noqa: E402
from small_cuts.space_hooks import install_relay_hooks  # noqa: E402
from small_cuts.viewer import THEME, build_viewer_app  # noqa: E402

init_sentry()

STARTUP_ERROR: str | None = None


def _allow_cpu_inference() -> bool:
    return os.environ.get("SMALL_CUTS_ALLOW_CPU_INFERENCE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _validate_startup_mode() -> None:
    if ON_SPACE and NEEDS_LOCAL_INFERENCE and spaces is None and not _allow_cpu_inference():
        raise RuntimeError(
            "refusing local inference on a Space without ZeroGPU; configure relay, engine, "
            "or Modal upload mode, or set SMALL_CUTS_ALLOW_CPU_INFERENCE=1 explicitly"
        )


def _degraded_app(message: str) -> gr.Blocks:
    with gr.Blocks(title="Small Cuts") as degraded:
        gr.Markdown(
            f"# Small Cuts is temporarily unavailable\n\nStartup configuration failed: `{message}`"
        )
    return degraded


def _build_demo() -> gr.Blocks:
    _validate_startup_mode()
    # In engine/relay/upload modes the Space is a public reader and upload front door, so it must
    # not warm local model weights. In local-inference mode, ZeroGPU loads lazily inside the
    # Gradio handler decorated with @spaces.GPU.
    app = build_viewer_app()
    install_relay_hooks(app.app)
    return app


try:
    demo = _build_demo()
except Exception as exc:
    capture_exception(exc)
    STARTUP_ERROR = str(exc)
    demo = _degraded_app(STARTUP_ERROR)


def launch_demo():
    return demo.launch(theme=THEME, _app=demo.app)


if __name__ == "__main__":
    launch_demo()
