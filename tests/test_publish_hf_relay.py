import importlib.util
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest


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


def test_notify_relay_hook_failure_is_non_fatal(monkeypatch, capsys):
    script = _load_publish_script()

    class Response:
        def raise_for_status(self):
            request = httpx.Request("POST", "https://space.example/hook")
            response = httpx.Response(503, request=request)
            raise httpx.HTTPStatusError("paused", request=request, response=response)

    monkeypatch.setattr(script.httpx, "post", lambda *args, **kwargs: Response())

    script.notify_relay_hook(
        SimpleNamespace(hook_url="https://space.example/hook", hook_token="secret"),
        SimpleNamespace(scene_count=2),
        bucket="macayaven/small-cuts-scenes-dev",
        prefix="relay",
    )

    assert "relay hook notify failed" in capsys.readouterr().err


def test_watch_mode_continues_after_transient_publish_failure(monkeypatch):
    script = _load_publish_script()
    calls = []

    def fake_publish_once(args):
        calls.append(args.watch)
        if len(calls) == 1:
            raise RuntimeError("temporary bucket failure")
        raise SystemExit(0)

    monkeypatch.setattr(script, "parse_args", lambda: SimpleNamespace(watch=True, interval=0))
    monkeypatch.setattr(script, "publish_once", fake_publish_once)
    monkeypatch.setattr(script, "init_sentry", lambda: None)
    monkeypatch.setattr(script, "capture_exception", lambda exc: None)
    monkeypatch.setattr(script.time, "sleep", lambda interval: None)

    try:
        script.main()
    except SystemExit as exc:
        assert exc.code == 0

    assert calls == [True, True]


@pytest.mark.parametrize("interval", ["0", "-1"])
def test_parse_args_rejects_nonpositive_interval_when_watch(monkeypatch, capsys, interval):
    script = _load_publish_script()
    monkeypatch.setattr(
        script.sys,
        "argv",
        ["publish_hf_relay.py", "--bucket", "macayaven/x", "--watch", "--interval", interval],
    )

    with pytest.raises(SystemExit) as exc_info:
        script.parse_args()

    assert exc_info.value.code == 2
    assert "--interval must be > 0 when --watch is set" in capsys.readouterr().err


def test_parse_args_allows_nonpositive_interval_without_watch(monkeypatch):
    script = _load_publish_script()
    monkeypatch.setattr(
        script.sys,
        "argv",
        ["publish_hf_relay.py", "--bucket", "macayaven/x", "--interval", "0"],
    )

    args = script.parse_args()

    assert args.watch is False
    assert args.interval == 0


def test_parse_args_keeps_positive_interval_when_watch(monkeypatch):
    script = _load_publish_script()
    monkeypatch.setattr(
        script.sys,
        "argv",
        ["publish_hf_relay.py", "--bucket", "macayaven/x", "--watch", "--interval", "1.5"],
    )

    args = script.parse_args()

    assert args.watch is True
    assert args.interval == 1.5
