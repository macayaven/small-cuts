"""Run the engine: `uv run python -m small_cuts.engine`."""

import os

import uvicorn

from .app import build_engine_app


def main() -> None:
    uvicorn.run(
        build_engine_app(),
        host="0.0.0.0",
        port=int(os.environ.get("SMALL_CUTS_ENGINE_PORT", "8077")),
    )


if __name__ == "__main__":
    main()
