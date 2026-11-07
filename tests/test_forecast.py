"""Tests for the heat pump start forecast."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.grid_peak_guard.forecast import StartForecast, temperature_band


def test_temperature_bands() -> None:
    assert temperature_band(-5) == "cold"
    assert temperature_band(2) == "mild"
    assert temperature_band(11.9) == "mild"
    assert temperature_band(12) == "warm"
    assert temperature_band(None) == "mild"


def _learn_days(fc: StartForecast, days: int, start_hour: int, temp: float) -> None:
    base = datetime(2026, 11, 1, tzinfo=UTC)
    for day in range(days):
        for hour in range(24):
            ts = base + timedelta(days=day, hours=hour)
            fc.observe_hour(ts, temp)
            if hour == start_hour:
                fc.record_start(ts + timedelta(minutes=10), temp)


def test_probability_per_band() -> None:
    fc = StartForecast()
    _learn_days(fc, 4, 6, -3.0)
    assert fc.probability(6, -3.0) == pytest.approx(1.0)
    assert fc.probability(7, -3.0) == 0.0
    # Other band has no data
    assert fc.probability(6, 15.0) == 0.0


def test_next_expected_start() -> None:
    fc = StartForecast()
    _learn_days(fc, 3, 6, -3.0)
    now = datetime(2026, 11, 5, 4, 30, tzinfo=UTC)
    nxt = fc.next_expected_start(now, -3.0)
    assert nxt is not None
    assert nxt[0] == datetime(2026, 11, 5, 6, 0, tzinfo=UTC)


def test_expected_extra_kw_external_start_has_precedence() -> None:
    fc = StartForecast()
    fc.record_run(1800, 3.0)
    now = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
    end = now + timedelta(minutes=15)
    # No learned starts -> nothing reserved
    assert fc.expected_extra_kw(now, end, 5.0) == 0.0
    # External start 5 min from now: runs 10 of the remaining 15 min at 3 kW
    extra = fc.expected_extra_kw(now, end, 5.0, now + timedelta(minutes=5))
    assert extra == pytest.approx(2.0)
    # External start after the window: nothing
    assert fc.expected_extra_kw(now, end, 5.0, end + timedelta(minutes=1)) == 0.0


def test_record_run_ema_and_roundtrip() -> None:
    fc = StartForecast()
    fc.record_run(600, 2.0)
    fc.record_run(1200, 4.0)
    assert fc.typical_kw == pytest.approx(2.4)
    assert fc.typical_runtime_s == pytest.approx(720)
    _learn_days(fc, 2, 3, 20.0)
    restored = StartForecast.from_dict(fc.as_dict())
    assert restored.as_dict() == fc.as_dict()
    assert StartForecast.from_dict({"starts": {"cold": [1]}}).starts["cold"] == [0] * 24
