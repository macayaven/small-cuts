from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .persistence import persistent_path

UPLOAD_BUDGET_DB_ENV = "SMALL_CUTS_UPLOAD_BUDGET_DB"
DAILY_GPU_BUDGET_SECONDS_ENV = "SMALL_CUTS_DAILY_GPU_BUDGET_SECONDS"
GPU_RESERVATION_SECONDS_ENV = "SMALL_CUTS_GPU_SECONDS_PER_UPLOAD_RESERVATION"
UPLOAD_RESERVATION_TTL_SECONDS_ENV = "SMALL_CUTS_UPLOAD_RESERVATION_TTL_SECONDS"
DEFAULT_BUDGET_DB = "~/.small-cuts/upload-budget.sqlite3"
DEFAULT_DAILY_LIMIT_S = 20 * 60
DEFAULT_RESERVE_S = 60
DEFAULT_RESERVATION_TTL_S = 30 * 60

_DAILY_SCHEMA = """\
CREATE TABLE IF NOT EXISTS upload_daily_budget (
    day TEXT PRIMARY KEY,
    used_s REAL NOT NULL DEFAULT 0,
    reserved_s REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
)"""
_RESERVATIONS_SCHEMA = """\
CREATE TABLE IF NOT EXISTS upload_reservations (
    reservation_id TEXT PRIMARY KEY,
    day TEXT NOT NULL,
    reserved_s REAL NOT NULL,
    created_at_s REAL NOT NULL,
    expires_at_s REAL NOT NULL
)"""
_RESERVATIONS_INDEX = """\
CREATE INDEX IF NOT EXISTS idx_upload_reservations_day_expiry
ON upload_reservations(day, expires_at_s)
"""
_NO_EXPIRY_S = 1.0e20


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
        reservation_ttl_s: float | None = None,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self.db_path = Path(
            db_path
            or os.environ.get(UPLOAD_BUDGET_DB_ENV)
            or persistent_path("upload-budget.sqlite3")
            or DEFAULT_BUDGET_DB
        )
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
        self.reservation_ttl_s = float(
            reservation_ttl_s
            if reservation_ttl_s is not None
            else os.environ.get(UPLOAD_RESERVATION_TTL_SECONDS_ENV, DEFAULT_RESERVATION_TTL_S)
        )
        self._now = now_fn or time.time
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA busy_timeout = 5000")
        self._db.execute(_DAILY_SCHEMA)
        self._db.execute(_RESERVATIONS_SCHEMA)
        self._db.execute(_RESERVATIONS_INDEX)
        self._migrate_legacy_reserved_seconds()

    @classmethod
    def from_env(cls) -> DailyProcessingBudget:
        return cls()

    def try_reserve(self, reserve_s: float | None = None) -> BudgetDecision:
        reserve = max(0.0, float(self.reserve_s if reserve_s is None else reserve_s))
        day = self._day_key()
        with self._lock:
            with self._transaction():
                self._ensure_day(day)
                self._expire_stale_reservations(day)
                used_s, reserved_s = self._totals(day)
                committed_s = used_s + reserved_s
                remaining_s = max(0.0, self.daily_limit_s - committed_s)
                if reserve > remaining_s:
                    return BudgetDecision(
                        allowed=False,
                        message="Demo daily GPU budget reached. Uploads reopen tomorrow.",
                        remaining_s=remaining_s,
                    )
                reservation_id = uuid.uuid4().hex
                now_s = self._now()
                expires_at_s = (
                    now_s + self.reservation_ttl_s if self.reservation_ttl_s > 0 else _NO_EXPIRY_S
                )
                self._db.execute(
                    """
                    INSERT INTO upload_reservations
                        (reservation_id, day, reserved_s, created_at_s, expires_at_s)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (reservation_id, day, reserve, now_s, expires_at_s),
                )
                self._db.execute(
                    "UPDATE upload_daily_budget SET updated_at = ? WHERE day = ?",
                    (self._now_iso(), day),
                )
            return BudgetDecision(
                allowed=True,
                token={"day": day, "reservation_id": reservation_id, "reserved_s": reserve},
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
        reservation_id = str(token.get("reservation_id") or "")
        with self._lock, self._transaction():
            self._ensure_day(day)
            if reservation_id:
                self._db.execute(
                    """
                    DELETE FROM upload_reservations
                    WHERE day = ? AND reservation_id = ?
                    """,
                    (day, reservation_id),
                )
            elif reserved_s > 0:
                self._release_reserved_seconds(day, reserved_s)
            self._db.execute(
                """
                UPDATE upload_daily_budget
                SET used_s = used_s + ?, reserved_s = 0, updated_at = ?
                WHERE day = ?
                """,
                (elapsed, self._now_iso(), day),
            )

    def seconds_used_today(self) -> float:
        with self._lock:
            day = self._day_key()
            with self._transaction():
                self._ensure_day(day)
                used_s, _ = self._totals(day)
        return used_s

    def seconds_committed_today(self) -> float:
        with self._lock:
            day = self._day_key()
            with self._transaction():
                self._ensure_day(day)
                self._expire_stale_reservations(day)
                used_s, reserved_s = self._totals(day)
        return used_s + reserved_s

    def close(self) -> None:
        self._db.close()

    def _day_key(self) -> str:
        return datetime.fromtimestamp(self._now(), tz=timezone.utc).date().isoformat()

    def _now_iso(self) -> str:
        return datetime.fromtimestamp(self._now(), tz=timezone.utc).isoformat()

    def _ensure_day(self, day: str) -> None:
        self._db.execute(
            """
            INSERT OR IGNORE INTO upload_daily_budget (day, used_s, reserved_s, updated_at)
            VALUES (?, 0, 0, ?)
            """,
            (day, self._now_iso()),
        )

    def _totals(self, day: str) -> tuple[float, float]:
        row = self._db.execute(
            "SELECT used_s FROM upload_daily_budget WHERE day = ?", (day,)
        ).fetchone()
        if row is None:
            return 0.0, 0.0
        reserved = self._db.execute(
            "SELECT COALESCE(SUM(reserved_s), 0) FROM upload_reservations WHERE day = ?",
            (day,),
        ).fetchone()
        return float(row[0]), float(reserved[0] if reserved is not None else 0.0)

    def _expire_stale_reservations(self, day: str) -> None:
        if self.reservation_ttl_s <= 0:
            return
        self._db.execute(
            "DELETE FROM upload_reservations WHERE day = ? AND expires_at_s <= ?",
            (day, self._now()),
        )

    def _release_reserved_seconds(self, day: str, reserved_s: float) -> None:
        remaining = reserved_s
        rows = self._db.execute(
            """
            SELECT reservation_id, reserved_s
            FROM upload_reservations
            WHERE day = ?
            ORDER BY created_at_s ASC, reservation_id ASC
            """,
            (day,),
        ).fetchall()
        for reservation_id, row_reserved_s in rows:
            if remaining <= 0:
                break
            row_reserved = float(row_reserved_s)
            if row_reserved <= remaining:
                self._db.execute(
                    "DELETE FROM upload_reservations WHERE reservation_id = ?",
                    (reservation_id,),
                )
                remaining -= row_reserved
            else:
                self._db.execute(
                    """
                    UPDATE upload_reservations
                    SET reserved_s = ?
                    WHERE reservation_id = ?
                    """,
                    (row_reserved - remaining, reservation_id),
                )
                remaining = 0

    def _migrate_legacy_reserved_seconds(self) -> None:
        with self._transaction():
            rows = self._db.execute(
                """
                SELECT day, reserved_s, updated_at
                FROM upload_daily_budget
                WHERE reserved_s > 0
                """
            ).fetchall()
            now_s = self._now()
            for day, reserved_s, updated_at in rows:
                reserved = float(reserved_s)
                if reserved <= 0:
                    continue
                parsed = _parse_updated_at(str(updated_at))
                created_at_s = parsed.timestamp() if parsed is not None else now_s
                if self.reservation_ttl_s > 0 and now_s - created_at_s > self.reservation_ttl_s:
                    continue
                self._db.execute(
                    """
                    INSERT OR IGNORE INTO upload_reservations
                        (reservation_id, day, reserved_s, created_at_s, expires_at_s)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        f"legacy-{day}",
                        str(day),
                        reserved,
                        created_at_s,
                        created_at_s + self.reservation_ttl_s
                        if self.reservation_ttl_s > 0
                        else _NO_EXPIRY_S,
                    ),
                )
            self._db.execute("UPDATE upload_daily_budget SET reserved_s = 0 WHERE reserved_s > 0")

    @contextmanager
    def _transaction(self):
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        else:
            self._db.execute("COMMIT")


def _parse_updated_at(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
