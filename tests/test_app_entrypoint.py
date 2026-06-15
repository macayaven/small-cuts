import importlib.util
import os
import sys
import warnings
from pathlib import Path

import gradio.oauth
from starlette.exceptions import StarletteDeprecationWarning


def _mock_gradio_oauth(monkeypatch):
    monkeypatch.setattr(
        gradio.oauth,
        "_get_mocked_oauth_info",
        lambda: {
            "access_token": "mock-oauth-token-for-ci",
            "token_type": "bearer",
            "expires_in": 3600,
            "id_token": "AAAAAAAAAAAAAAAAAAAAAAAAAA",
            "scope": "openid profile",
            "expires_at": 9999999999,
            "userinfo": {
                "sub": "11111111111111111111111",
                "name": "CI User",
                "preferred_username": "ci-user",
                "profile": "https://huggingface.co/ci-user",
                "picture": "",
                "website": "",
                "aud": "00000000-0000-0000-0000-000000000000",
                "auth_time": 1691672844,
                "nonce": "aaaaaaaaaaaaaaaaaaa",
                "iat": 1691672844,
                "exp": 1691676444,
                "iss": "https://huggingface.co",
            },
        },
    )


def test_space_engine_mode_does_not_force_local_backends(monkeypatch):
    monkeypatch.setenv("SPACE_ID", "build-small-hackathon/small-cuts")
    monkeypatch.setenv("SMALL_CUTS_ENGINE_URL", "http://127.0.0.1:9")
    monkeypatch.delenv("SMALL_CUTS_RELAY_BUCKET", raising=False)
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


def test_space_bucket_relay_mode_does_not_force_local_backends(monkeypatch):
    monkeypatch.setenv("SPACE_ID", "build-small-hackathon/small-cuts-live")
    monkeypatch.delenv("SMALL_CUTS_ENGINE_URL", raising=False)
    monkeypatch.setenv("SMALL_CUTS_RELAY_BUCKET", "build-small-hackathon/small-cuts-scenes")
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)
    monkeypatch.delenv("SMALL_CUTS_TTS_BACKEND", raising=False)
    monkeypatch.setitem(sys.modules, "spaces", None)

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    spec = importlib.util.spec_from_file_location("_small_cuts_test_app_relay", app_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert os.environ.get("SMALL_CUTS_BACKEND") is None
    assert os.environ.get("SMALL_CUTS_TTS_BACKEND") is None


def test_space_relay_with_modal_upload_does_not_force_local_backends(monkeypatch):
    monkeypatch.setenv("SPACE_ID", "build-small-hackathon/small-cuts-live")
    monkeypatch.delenv("SMALL_CUTS_ENGINE_URL", raising=False)
    monkeypatch.setenv("SMALL_CUTS_RELAY_BUCKET", "build-small-hackathon/small-cuts-scenes")
    monkeypatch.setenv("SMALL_CUTS_ENABLE_UPLOAD_SANDBOX", "1")
    monkeypatch.setenv("SMALL_CUTS_MODAL_API_URL", "https://example.modal.run")
    monkeypatch.delenv("SMALL_CUTS_BACKEND", raising=False)
    monkeypatch.delenv("SMALL_CUTS_TTS_BACKEND", raising=False)
    monkeypatch.setitem(sys.modules, "spaces", None)
    _mock_gradio_oauth(monkeypatch)

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    spec = importlib.util.spec_from_file_location("_small_cuts_test_app_modal", app_path)
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
