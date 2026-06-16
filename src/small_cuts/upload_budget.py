from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UPLOAD_BUDGET_DB_ENV = "SMALL_CUTS_UPLOAD_BUDGET_DB"
DAILY_GPU_BUDGET_SECONDS_ENV = "SMALL_CUTS_DAILY_GPU_BUDGET_SECONDS"
GPU_RESERVATION_SECONDS_ENV = "SMALL_CUTS_GPU_SECONDS_PER_UPLOAD_RESERVATION"
DEFAULT_BUDGET_DB = "~/.small-cuts/upload-budget.sqlite3"
DEFAULT_DAILY_LIMIT_S = 20 * 60
DEFAULT_RESERVE_S = 60

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS upload_daily_budget (
    day TEXT PRIMARY KEY,
    used_s REAL NOT NULL DEFAULT 0,
    reserved_s REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
)"""


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    token: dict[str, Any] | None = None
    message: str = ""
    remaining_s: float = 0.0


class DailyProcessingBudget:
    """Global daily upload-processing budget.

    The budget is intentionally identity-free. It protects demo GPU credits by tracking committed
    processing seconds for the current UTC day. A preflight reservation counts against the limit
    immediately, so queued concurrent requests cannot all pass the same remaining-capacity check.
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        daily_limit_s: float | None = None,
        reserve_s: float | None = None,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self.db_path = Path(db_path or os.environ.get(UPLOAD_BUDGET_DB_ENV) or DEFAULT_BUDGET_DB)
        self.db_path = self.db_path.expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.daily_limit_s = float(
            daily_limit_s
            if daily_limit_s is not None
            else os.environ.get(DAILY_GPU_BUDGET_SECONDS_ENV, DEFAULT_DAILY_LIMIT_S)
        )
        self.reserve_s = float(
            reserve_s
            if reserve_s is not None
            else os.environ.get(GPU_RESERVATION_SECONDS_ENV, DEFAULT_RESERVE_S)
        )
        self._now = now_fn or time.time
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.db_path, check_same_thread=False)
        self._db.execute(_SCHEMA)
        self._db.commit()

    @classmethod
    def from_env(cls) -> DailyProcessingBudget:
        return cls()

    def try_reserve(self, reserve_s: float | None = None) -> BudgetDecision:
        reserve = max(0.0, float(self.reserve_s if reserve_s is None else reserve_s))
        day = self._day_key()
        with self._lock:
            self._ensure_day(day)
            used_s, reserved_s = self._totals(day)
            committed_s = used_s + reserved_s
            remaining_s = max(0.0, self.daily_limit_s - committed_s)
            if reserve > remaining_s:
                return BudgetDecision(
                    allowed=False,
                    message="Demo daily GPU budget reached. Uploads reopen tomorrow.",
                    remaining_s=remaining_s,
                )
            with self._db:
                self._db.execute(
                    """
                    UPDATE upload_daily_budget
                    SET reserved_s = reserved_s + ?, updated_at = datetime('now')
                    WHERE day = ?
                    """,
                    (reserve, day),
                )
            return BudgetDecision(
                allowed=True,
                token={"day": day, "reserved_s": reserve},
                remaining_s=max(0.0, remaining_s - reserve),
            )

    def finish(self, token: Any, elapsed_s: float) -> None:
        if not isinstance(token, dict):
            return
        day = str(token.get("day") or "")
        if not day:
            return
        reserved_s = max(0.0, float(token.get("reserved_s") or 0.0))
        elapsed = max(0.0, float(elapsed_s or 0.0))
        with self._lock:
            self._ensure_day(day)
            with self._db:
                self._db.execute(
                    """
                    UPDATE upload_daily_budget
                    SET used_s = used_s + ?,
                        reserved_s = CASE
                            WHEN reserved_s >= ? THEN reserved_s - ?
                            ELSE 0
                        END,
                        updated_at = datetime('now')
                    WHERE day = ?
                    """,
                    (elapsed, reserved_s, reserved_s, day),
                )

    def seconds_used_today(self) -> float:
        with self._lock:
            day = self._day_key()
            self._ensure_day(day)
            used_s, _ = self._totals(day)
        return used_s

    def seconds_committed_today(self) -> float:
        with self._lock:
            day = self._day_key()
            self._ensure_day(day)
            used_s, reserved_s = self._totals(day)
        return used_s + reserved_s

    def close(self) -> None:
        self._db.close()

    def _day_key(self) -> str:
        return datetime.fromtimestamp(self._now(), tz=timezone.utc).date().isoformat()

    def _ensure_day(self, day: str) -> None:
        with self._db:
            self._db.execute(
                """
                INSERT OR IGNORE INTO upload_daily_budget (day, used_s, reserved_s, updated_at)
                VALUES (?, 0, 0, datetime('now'))
                """,
                (day,),
            )

    def _totals(self, day: str) -> tuple[float, float]:
        row = self._db.execute(
            "SELECT used_s, reserved_s FROM upload_daily_budget WHERE day = ?", (day,)
        ).fetchone()
        if row is None:
            return 0.0, 0.0
        return float(row[0]), float(row[1])
