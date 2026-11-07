"""Pure calculations for Grid Peak Guard.

This module must not import Home Assistant so it can be tested in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

SECONDS_PER_HOUR = 3600.0

REASON_IDLE = "idle"
REASON_HOLD = "hold"
REASON_ESCALATE = "escalate"
REASON_HARD_LIMIT = "hard_limit"
REASON_SETTLING = "settling"


def window_bounds(now: datetime, window_minutes: int) -> tuple[datetime, datetime]:
    """Return start and end of the measuring window containing ``now``.

    Windows are aligned to the Unix epoch, which matches quarter-hour meter
    windows in every time zone with an offset that is a multiple of the window.
    Working on timestamps keeps the result correct across DST changes.
    """
    window_s = window_minutes * 60
    ts = now.timestamp()
    start_ts = ts - (ts % window_s)
    # Build both bounds from timestamps: aware datetime + timedelta is
    # wall-clock arithmetic and would be wrong across a DST change.
    start = datetime.fromtimestamp(start_ts, tz=now.tzinfo)
    end = datetime.fromtimestamp(start_ts + window_s, tz=now.tzinfo)
    return start, end


def projected_energy_kwh(
    energy_kwh: float, current_kw: float, extra_kw: float, remaining_s: float
) -> float:
    """Window energy + (current import + expected extra load) x remaining time."""
    remaining_h = max(remaining_s, 0.0) / SECONDS_PER_HOUR
    return energy_kwh + max(current_kw + extra_kw, 0.0) * remaining_h


def projected_average_kw(
    energy_kwh: float,
    current_kw: float,
    extra_kw: float,
    remaining_s: float,
    window_s: float,
) -> float:
    """Projected average import over the whole window in kW."""
    if window_s <= 0:
        return 0.0
    energy = projected_energy_kwh(energy_kwh, current_kw, extra_kw, remaining_s)
    return energy * SECONDS_PER_HOUR / window_s


def effective_limit_kw(
    target_kw: float, minimum_kw: float, month_peak_kw: float, use_month_peak: bool
) -> float:
    """Effective limit = max(target, billed minimum, month peak so far).

    Reducing below a peak that is already billed for this month saves nothing,
    so the month peak raises the limit when enabled.
    """
    limit = max(target_kw, minimum_kw)
    if use_month_peak:
        limit = max(limit, month_peak_kw)
    return limit


def required_reduction_kw(
    energy_kwh: float,
    current_kw: float,
    extra_kw: float,
    remaining_s: float,
    window_s: float,
    limit_kw: float,
) -> float:
    """Power that must be shed for the rest of the window to meet the limit."""
    if remaining_s <= 0:
        return 0.0
    allowed_kwh = limit_kw * window_s / SECONDS_PER_HOUR
    excess_kwh = (
        projected_energy_kwh(energy_kwh, current_kw, extra_kw, remaining_s)
        - allowed_kwh
    )
    return max(excess_kwh * SECONDS_PER_HOUR / remaining_s, 0.0)


@dataclass(frozen=True, slots=True)
class EscalationDecision:
    """Result of an escalation step."""

    level: int
    reason: str


def next_escalation(
    *,
    projected_kw: float,
    limit_kw: float,
    hard_limit_kw: float,
    current_level: int,
    max_level: int,
    elapsed_s: float,
    settle_s: float,
    seconds_since_change: float,
    wait_s: float,
) -> EscalationDecision:
    """Decide the escalation level for this cycle.

    * One additional stage per waiting time while the projection exceeds the
      limit; the first stage is taken without waiting.
    * At or above the hard limit all stages are engaged at once.
    * Stages are never released here; release happens at window end (or by a
      device's own protection limits).
    * During the first ``settle_s`` seconds of a window the projection is too
      noisy, so nothing is escalated.
    """
    if max_level <= 0:
        return EscalationDecision(0, REASON_IDLE)
    if elapsed_s < settle_s:
        return EscalationDecision(
            current_level, REASON_SETTLING if current_level == 0 else REASON_HOLD
        )
    if projected_kw >= hard_limit_kw:
        return EscalationDecision(max_level, REASON_HARD_LIMIT)
    if (
        projected_kw > limit_kw
        and current_level < max_level
        and (current_level == 0 or seconds_since_change >= wait_s)
    ):
        return EscalationDecision(current_level + 1, REASON_ESCALATE)
    return EscalationDecision(
        current_level, REASON_HOLD if current_level else REASON_IDLE
    )


def billed_power_kw(peak_kw: float, minimum_kw: float) -> float:
    """Power that is billed for the month."""
    return max(peak_kw, minimum_kw)


def monthly_power_cost(
    peak_kw: float,
    price_per_kw: float,
    minimum_kw: float,
    threshold_kw: float,
    factor_above: float,
) -> float:
    """Monthly power charge; power above ``threshold_kw`` is weighted by ``factor_above``."""
    billed = billed_power_kw(peak_kw, minimum_kw)
    base = min(billed, threshold_kw)
    above = max(billed - threshold_kw, 0.0)
    return price_per_kw * (base + above * factor_above)
