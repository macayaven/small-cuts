"""Home-node narration engine — mobile-facing WebSocket session (Team Inference).

Optional install: `uv sync --extra engine`. Nothing in the existing app path
imports this package, so the Space/UI keep working without the extra.
"""

from .app import build_engine_app

__all__ = ["build_engine_app"]
