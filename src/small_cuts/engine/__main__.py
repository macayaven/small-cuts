"""Run the engine: `uv run python -m small_cuts.engine`."""

import contextlib
import os
import signal

import uvicorn

from .app import build_engine_app


def main() -> None:
    from small_cuts import narrator

    def shutdown(signum, frame):  # noqa: ARG001
        with contextlib.suppress(Exception):
            backend = narrator.get_backend()
            close = getattr(backend, "close", None)
            if close is not None:
                close()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, shutdown)
    uvicorn.run(
        build_engine_app(),
        host=os.environ.get("SMALL_CUTS_ENGINE_HOST", "0.0.0.0"),
        port=int(os.environ.get("SMALL_CUTS_ENGINE_PORT", "8077")),
        ws_max_size=int(os.environ.get("SMALL_CUTS_ENGINE_WS_MAX_SIZE", str(64 * 1024 * 1024))),
    )


if __name__ == "__main__":
    main()
