import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_publish_script():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "publish_hf_relay.py"
    spec = importlib.util.spec_from_file_location("_small_cuts_publish_hf_relay", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_notify_relay_hook_skips_without_url(monkeypatch):
    script = _load_publish_script()
    calls = []
    monkeypatch.setattr(script.httpx, "post", lambda *args, **kwargs: calls.append((args, kwargs)))

    script.notify_relay_hook(
        SimpleNamespace(hook_url="", hook_token=""),
        SimpleNamespace(scene_count=2),
        bucket="macayaven/small-cuts-scenes-dev",
        prefix="relay",
    )

    assert calls == []


def test_notify_relay_hook_posts_bearer(monkeypatch):
    script = _load_publish_script()
    calls = []

    class Response:
        def raise_for_status(self):
            calls.append(("raise_for_status",))

    def fake_post(url, *, headers, json, timeout):
        calls.append((url, headers, json, timeout))
        return Response()

    monkeypatch.setattr(script.httpx, "post", fake_post)

    script.notify_relay_hook(
        SimpleNamespace(
            hook_url="https://space.example/small-cuts/hooks/relay-scene",
            hook_token="secret",
        ),
        SimpleNamespace(scene_count=2),
        bucket="macayaven/small-cuts-scenes-dev",
        prefix="relay",
    )

    assert calls == [
        (
            "https://space.example/small-cuts/hooks/relay-scene",
            {"Authorization": "Bearer secret"},
            {
                "bucket": "macayaven/small-cuts-scenes-dev",
                "prefix": "relay",
                "scene_count": 2,
            },
            5.0,
        ),
        ("raise_for_status",),
    ]
