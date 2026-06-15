"""Optional Sentry observability for demo/runtime failures.

No Sentry traffic is sent unless ``SENTRY_DSN`` is configured. Payload scrubbing
keeps frames, audio, cookies, and auth headers out of events.
"""

from __future__ import annotations

import os
from typing import Any

SENTRY_DSN_ENV = "SENTRY_DSN"
SENTRY_ENV_ENV = "SENTRY_ENVIRONMENT"
SENTRY_RELEASE_ENV = "SENTRY_RELEASE"
SENSITIVE_HEADERS = {"authorization", "cookie", "x-api-key", "x-forwarded-for"}

_INITIALIZED = False


def init_sentry(dsn: str | None = None, *, sdk: Any | None = None) -> bool:
    global _INITIALIZED
    dsn = dsn if dsn is not None else os.environ.get(SENTRY_DSN_ENV, "").strip()
    if not dsn:
        return False
    if _INITIALIZED:
        return True
    sdk = sdk or _import_sentry_sdk()
    if sdk is None:
        return False
    sdk.init(
        dsn=dsn,
        environment=os.environ.get(SENTRY_ENV_ENV) or os.environ.get("SPACE_ID") or "local",
        release=os.environ.get(SENTRY_RELEASE_ENV) or os.environ.get("SPACE_COMMIT_SHA"),
        send_default_pii=False,
        attach_stacktrace=True,
        traces_sample_rate=0.0,
        before_send=_scrub_event,
    )
    _INITIALIZED = True
    return True


def capture_exception(exc: BaseException, *, sdk: Any | None = None) -> None:
    if not _INITIALIZED and not init_sentry(sdk=sdk):
        return
    sdk = sdk or _import_sentry_sdk()
    if sdk is not None:
        sdk.capture_exception(exc)


def _import_sentry_sdk() -> Any | None:
    try:
        import sentry_sdk
    except ImportError:
        return None
    return sentry_sdk


def _scrub_event(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                key: value for key, value in headers.items() if key.lower() not in SENSITIVE_HEADERS
            }
    return event


def reset_for_tests() -> None:
    global _INITIALIZED
    _INITIALIZED = False
