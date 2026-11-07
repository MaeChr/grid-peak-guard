"""Start forecast for heat pumps (no Home Assistant imports).

Learns how often a heat pump starts in a given hour of the day, separately per
outdoor temperature band, plus typical power and runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .const import (
    BAND_COLD,
    BAND_MILD,
    BAND_WARM,
    BANDS,
    FORECAST_MIN_PROBABILITY,
    TEMP_BAND_COLD_BELOW,
    TEMP_BAND_WARM_FROM,
)

# Weight of a new sample in the exponential moving averages.
EMA_ALPHA = 0.2


def temperature_band(outdoor_c: float | None) -> str:
    """Map an outdoor temperature to a band (cold < 2 °C <= mild < 12 °C <= warm)."""
    if outdoor_c is None:
        return BAND_MILD
    if outdoor_c < TEMP_BAND_COLD_BELOW:
        return BAND_COLD
    if outdoor_c < TEMP_BAND_WARM_FROM:
        return BAND_MILD
    return BAND_WARM


def _ema(old: float | None, new: float) -> float:
    return new if old is None else old + EMA_ALPHA * (new - old)


@dataclass
class StartForecast:
    """Learned start statistics of one heat pump."""

    starts: dict[str, list[int]] = field(
        default_factory=lambda: {band: [0] * 24 for band in BANDS}
    )
    observed: dict[str, list[int]] = field(
        default_factory=lambda: {band: [0] * 24 for band in BANDS}
    )
    typical_kw: float | None = None
    typical_runtime_s: float | None = None
    _last_hour_key: str | None = None

    # -- learning -----------------------------------------------------------

    def observe_hour(self, now: datetime, outdoor_c: float | None) -> None:
        """Count each local clock hour once as observed (for probabilities)."""
        key = now.strftime("%Y%m%d%H")
        if key == self._last_hour_key:
            return
        self._last_hour_key = key
        self.observed[temperature_band(outdoor_c)][now.hour] += 1

    def record_start(self, start: datetime, outdoor_c: float | None) -> None:
        """Record a start in the hour/band it happened."""
        self.observe_hour(start, outdoor_c)
        band = temperature_band(outdoor_c)
        hour = start.hour
        # A start cannot be more frequent than observed hours for probability.
        self.starts[band][hour] = min(
            self.starts[band][hour] + 1, self.observed[band][hour]
        )

    def record_run(self, runtime_s: float, mean_kw: float) -> None:
        """Record the duration and mean power of a finished run."""
        if runtime_s > 0:
            self.typical_runtime_s = _ema(self.typical_runtime_s, runtime_s)
        if mean_kw > 0:
            self.typical_kw = _ema(self.typical_kw, mean_kw)

    # -- prediction ---------------------------------------------------------

    def probability(self, hour: int, outdoor_c: float | None) -> float:
        """Probability that a start happens in ``hour`` for this temperature."""
        band = temperature_band(outdoor_c)
        observed = self.observed[band][hour % 24]
        if observed == 0:
            return 0.0
        return min(self.starts[band][hour % 24] / observed, 1.0)

    def next_expected_start(
        self,
        now: datetime,
        outdoor_c: float | None,
        min_probability: float = FORECAST_MIN_PROBABILITY,
    ) -> tuple[datetime, float] | None:
        """First upcoming hour (including the current one) with a likely start."""
        base = now.replace(minute=0, second=0, microsecond=0)
        for offset in range(24):
            slot = base + timedelta(hours=offset)
            prob = self.probability(slot.hour, outdoor_c)
            if prob >= min_probability:
                return (max(slot, now), prob)
        return None

    def expected_extra_kw(
        self,
        now: datetime,
        window_end: datetime,
        outdoor_c: float | None,
        external_start: datetime | None = None,
    ) -> float:
        """Return the expected average extra load for the rest of the window (budget reserve).

        An external start time takes precedence over the learned statistics.
        """
        remaining_s = (window_end - now).total_seconds()
        if remaining_s <= 0 or not self.typical_kw:
            return 0.0
        runtime_s = self.typical_runtime_s or remaining_s
        if external_start is not None:
            start, probability = external_start, 1.0
        else:
            nxt = self.next_expected_start(now, outdoor_c)
            if nxt is None:
                return 0.0
            start, probability = nxt
            # The probability covers a whole hour; spread it over the hour.
            probability *= min(remaining_s / 3600.0, 1.0)
        start = max(start, now)
        if start >= window_end:
            return 0.0
        overlap_s = min((window_end - start).total_seconds(), runtime_s)
        return probability * self.typical_kw * overlap_s / remaining_s

    # -- persistence --------------------------------------------------------

    def as_dict(self) -> dict:
        """Serialize for storage."""
        return {
            "starts": self.starts,
            "observed": self.observed,
            "typical_kw": self.typical_kw,
            "typical_runtime_s": self.typical_runtime_s,
            "last_hour_key": self._last_hour_key,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> StartForecast:
        """Restore from storage; invalid data yields an empty forecast."""
        fc = cls()
        if not data:
            return fc
        for attr in ("starts", "observed"):
            raw = data.get(attr) or {}
            for band in BANDS:
                values = raw.get(band)
                if isinstance(values, list) and len(values) == 24:
                    getattr(fc, attr)[band] = [int(v) for v in values]
        fc.typical_kw = data.get("typical_kw")
        fc.typical_runtime_s = data.get("typical_runtime_s")
        fc._last_hour_key = data.get("last_hour_key")
        return fc
