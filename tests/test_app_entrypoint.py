import importlib.util
import os
import sys
import warnings
from pathlib import Path

from starlette.exceptions import StarletteDeprecationWarning


def test_space_engine_mode_does_not_force_local_backends(monkeypatch):
    monkeypatch.setenv("SPACE_ID", "build-small-hackathon/small-cuts")
    monkeypatch.setenv("SMALL_CUTS_ENGINE_URL", "http://127.0.0.1:9")
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)
    monkeypatch.delenv("SMALL_CUTS_TTS_BACKEND", raising=False)
    monkeypatch.setitem(sys.modules, "spaces", None)

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    spec = importlib.util.spec_from_file_location("_small_cuts_test_app", app_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert os.environ.get("SMALL_CUTS_BACKEND") is None
    assert os.environ.get("SMALL_CUTS_TTS_BACKEND") is None


def test_app_filters_gradio_starlette_queue_warning(monkeypatch):
    monkeypatch.setenv("SMALL_CUTS_ENGINE_URL", "http://127.0.0.1:9")

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    spec = importlib.util.spec_from_file_location("_small_cuts_test_app_warnings", app_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with warnings.catch_warnings(record=True) as caught:
        warnings.warn(
            "'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. "
            "Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.",
            StarletteDeprecationWarning,
            stacklevel=1,
        )

    assert caught == []
