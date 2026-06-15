from small_cuts import observability


class FakeSentrySdk:
    def __init__(self):
        self.init_calls = []
        self.captured = []

    def init(self, **kwargs):
        self.init_calls.append(kwargs)

    def capture_exception(self, exc):
        self.captured.append(exc)


def test_sentry_init_is_noop_without_dsn(monkeypatch):
    fake = FakeSentrySdk()
    monkeypatch.delenv(observability.SENTRY_DSN_ENV, raising=False)
    observability.reset_for_tests()

    assert observability.init_sentry(sdk=fake) is False
    assert fake.init_calls == []


def test_sentry_init_scrubs_request_payload(monkeypatch):
    fake = FakeSentrySdk()
    monkeypatch.setenv(observability.SENTRY_DSN_ENV, "https://example@sentry.invalid/1")
    monkeypatch.setenv("SPACE_ID", "build-small-hackathon/small-cuts-live")
    observability.reset_for_tests()

    assert observability.init_sentry(sdk=fake) is True
    (kwargs,) = fake.init_calls
    assert kwargs["send_default_pii"] is False
    assert kwargs["traces_sample_rate"] == 0.0
    event = {
        "request": {
            "data": "frame bytes",
            "cookies": "session",
            "headers": {"authorization": "secret", "content-type": "application/json"},
            "url": "https://example.test/v1/scenes",
        }
    }

    scrubbed = kwargs["before_send"](event, {})

    assert "data" not in scrubbed["request"]
    assert "cookies" not in scrubbed["request"]
    assert scrubbed["request"]["headers"] == {"content-type": "application/json"}


def test_capture_exception_requires_initialized_sentry(monkeypatch):
    fake = FakeSentrySdk()
    observability.reset_for_tests()
    monkeypatch.delenv(observability.SENTRY_DSN_ENV, raising=False)

    exc = RuntimeError("boom")
    observability.capture_exception(exc, sdk=fake)
    assert fake.captured == []

    monkeypatch.setenv(observability.SENTRY_DSN_ENV, "https://example@sentry.invalid/1")
    observability.capture_exception(exc, sdk=fake)
    assert fake.captured == [exc]
