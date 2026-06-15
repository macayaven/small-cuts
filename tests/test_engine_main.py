from small_cuts.engine import __main__ as engine_main


def test_engine_entrypoint_sets_websocket_payload_budget(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("SMALL_CUTS_LIBRARY_DIR", str(tmp_path / "library"))
    monkeypatch.setattr(engine_main.uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))

    engine_main.main()

    assert calls[0]["host"] == "127.0.0.1"
    assert calls[0]["ws_max_size"] == 64 * 1024 * 1024


def test_engine_entrypoint_allows_explicit_host_override(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("SMALL_CUTS_LIBRARY_DIR", str(tmp_path / "library"))
    monkeypatch.setenv("SMALL_CUTS_ENGINE_HOST", "0.0.0.0")
    monkeypatch.setattr(engine_main.uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))

    engine_main.main()

    assert calls[0]["host"] == "0.0.0.0"
