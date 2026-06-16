from __future__ import annotations

from small_cuts.upload_budget import DailyProcessingBudget


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


def test_unfinished_reservation_counts_against_hard_limit(tmp_path):
    budget = DailyProcessingBudget(
        tmp_path / "budget.sqlite3",
        daily_limit_s=60,
        reserve_s=60,
    )

    first = budget.try_reserve()
    second = budget.try_reserve()

    assert first.allowed is True
    assert second.allowed is False
