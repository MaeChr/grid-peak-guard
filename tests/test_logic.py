"""Tests for the pure calculation module."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.grid_peak_guard import logic


def test_window_bounds_quarter_hour() -> None:
    now = datetime(2026, 11, 2, 10, 7, 33, tzinfo=UTC)
    start, end = logic.window_bounds(now, 15)
    assert start == datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
    assert end - start == timedelta(minutes=15)


def test_window_bounds_dst_change_vienna() -> None:
    tz = ZoneInfo("Europe/Vienna")
    # 2026-10-25 02:00-03:00 occurs twice; the second occurrence is fold=1.
    now = datetime(2026, 10, 25, 2, 20, tzinfo=tz, fold=1)
    start, end = logic.window_bounds(now, 15)
    assert start.timestamp() == pytest.approx(now.timestamp() - 5 * 60)
    assert end.timestamp() - start.timestamp() == 900


def test_projection() -> None:
    # 1 kWh after 5 min, 6 kW for remaining 10 min -> (1 + 1) kWh / 0.25 h = 8 kW
    assert logic.projected_average_kw(1.0, 6.0, 0.0, 600, 900) == pytest.approx(8.0)
    # extra load is added to the current import
    assert logic.projected_average_kw(1.0, 5.0, 1.0, 600, 900) == pytest.approx(8.0)
    # negative sum is clipped
    assert logic.projected_average_kw(1.0, -3.0, 0.0, 600, 900) == pytest.approx(4.0)


def test_effective_limit() -> None:
    assert logic.effective_limit_kw(5, 2, 7, True) == 7
    assert logic.effective_limit_kw(5, 2, 7, False) == 5
    assert logic.effective_limit_kw(1, 2, 0, True) == 2


def test_required_reduction() -> None:
    # Projection 8 kW, limit 5 kW: excess 0.75 kWh over 10 min -> 4.5 kW
    assert logic.required_reduction_kw(1.0, 6.0, 0.0, 600, 900, 5.0) == pytest.approx(
        4.5
    )
    assert logic.required_reduction_kw(0.1, 1.0, 0.0, 600, 900, 5.0) == 0.0
    assert logic.required_reduction_kw(3.0, 6.0, 0.0, 0, 900, 5.0) == 0.0


def _decide(**kw):
    args = {
        "projected_kw": 6.0,
        "limit_kw": 5.0,
        "hard_limit_kw": 7.0,
        "current_level": 0,
        "max_level": 3,
        "elapsed_s": 120,
        "settle_s": 30,
        "seconds_since_change": 0,
        "wait_s": 60,
    }
    args.update(kw)
    return logic.next_escalation(**args)


def test_escalation_first_stage_immediately() -> None:
    assert _decide() == logic.EscalationDecision(1, logic.REASON_ESCALATE)


def test_escalation_waits_between_stages() -> None:
    assert _decide(current_level=1, seconds_since_change=30).level == 1
    assert _decide(current_level=1, seconds_since_change=60).level == 2
    assert _decide(current_level=3, seconds_since_change=600).level == 3


def test_escalation_hard_limit_engages_all() -> None:
    assert _decide(projected_kw=7.0) == logic.EscalationDecision(
        3, logic.REASON_HARD_LIMIT
    )


def test_escalation_settling_and_no_release() -> None:
    assert _decide(elapsed_s=10).reason == logic.REASON_SETTLING
    # Below the limit the level is held, never released here.
    assert _decide(projected_kw=1.0, current_level=2).level == 2
    assert _decide(max_level=0).reason == logic.REASON_IDLE


def test_monthly_power_cost() -> None:
    # minimum 2 kW applies
    assert logic.monthly_power_cost(1.0, 3.0, 2.0, 10.0, 2.0) == pytest.approx(6.0)
    # 12 kW: 10 kW normal + 2 kW double
    assert logic.monthly_power_cost(12.0, 3.0, 2.0, 10.0, 2.0) == pytest.approx(42.0)
