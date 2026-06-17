from __future__ import annotations

from small_cuts.upload_budget import DailyProcessingBudget


def test_daily_budget_defaults_under_configured_bucket_mount(monkeypatch, tmp_path):
    mount = tmp_path / "bucket"
    monkeypatch.delenv("SMALL_CUTS_UPLOAD_BUDGET_DB", raising=False)
    monkeypatch.setenv("SMALL_CUTS_BUCKET_MOUNT_PATH", str(mount))

    budget = DailyProcessingBudget.from_env()

    assert budget.db_path == (mount / "space" / "upload-budget.sqlite3").resolve()
    budget.close()


def test_daily_budget_reserves_capacity_and_charges_elapsed_processing_time(tmp_path):
    current = 1_800_000_000.0
    budget = DailyProcessingBudget(
        tmp_path / "budget.sqlite3",
        daily_limit_s=120,
        reserve_s=60,
        now_fn=lambda: current,
    )

    first = budget.try_reserve()

    assert first.allowed is True
    assert first.token is not None
    assert budget.seconds_committed_today() == 60

    budget.finish(first.token, elapsed_s=70)

    assert budget.seconds_used_today() == 70
    assert budget.seconds_committed_today() == 70

    second = budget.try_reserve()

    assert second.allowed is False
    assert second.token is None
    assert "Demo daily GPU budget reached" in second.message


def test_daily_budget_resets_on_next_utc_day(tmp_path):
    current = 1_800_000_000.0
    budget = DailyProcessingBudget(
        tmp_path / "budget.sqlite3",
        daily_limit_s=60,
        reserve_s=60,
        now_fn=lambda: current,
    )
    first = budget.try_reserve()
    assert first.allowed is True

    current += 24 * 60 * 60
    next_day = budget.try_reserve()

    assert next_day.allowed is True
    assert next_day.token is not None


def test_unfinished_reservation_counts_against_hard_limit_until_ttl(tmp_path):
    current = 1_800_000_000.0
    budget = DailyProcessingBudget(
        tmp_path / "budget.sqlite3",
        daily_limit_s=60,
        reserve_s=60,
        reservation_ttl_s=120,
        now_fn=lambda: current,
    )

    first = budget.try_reserve()
    second = budget.try_reserve()

    assert first.allowed is True
    assert second.allowed is False

    current += 121
    third = budget.try_reserve()

    assert third.allowed is True
    assert third.token is not None


def test_stale_reservations_expire_independently_of_newer_reservations(tmp_path):
    current = 1_800_000_000.0
    budget = DailyProcessingBudget(
        tmp_path / "budget.sqlite3",
        daily_limit_s=120,
        reserve_s=60,
        reservation_ttl_s=120,
        now_fn=lambda: current,
    )

    first = budget.try_reserve()
    assert first.allowed is True

    current += 90
    second = budget.try_reserve()
    assert second.allowed is True

    current += 31
    third = budget.try_reserve()

    assert third.allowed is True
    assert third.token is not None
    assert budget.seconds_committed_today() == 120


def test_reservations_use_immediate_write_transaction(tmp_path):
    budget = DailyProcessingBudget(
        tmp_path / "budget.sqlite3",
        daily_limit_s=60,
        reserve_s=60,
        now_fn=lambda: 1_800_000_000.0,
    )
    statements = []
    budget._db.set_trace_callback(statements.append)

    decision = budget.try_reserve()

    assert decision.allowed is True
    assert "BEGIN IMMEDIATE" in [statement.strip().upper() for statement in statements]
