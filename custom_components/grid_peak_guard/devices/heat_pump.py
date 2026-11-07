"""Heat pump: optional lock (EVU contact, SG-Ready, setpoint) with protection times."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from ..forecast import StartForecast
from .base import (
    COMMON_FIELDS,
    KIND_BOOL,
    KIND_ENTITY,
    KIND_NUMBER,
    KIND_TEXT,
    NUMBER_DOMAINS,
    ON_OFF_DOMAINS,
    SELECT_DOMAINS,
    BaseDevice,
    FieldSpec,
    register,
    state_to_float,
)


@register
class HeatPumpDevice(BaseDevice):
    """Heat pump with learning start forecast.

    Protection (never weakened):
    * minimum runtime: a running compressor is not locked before it ran
      ``min_runtime_min``;
    * maximum lock duration per intervention (``max_block_min``);
    * maximum lock time per day (``max_block_day_min``);
    * minimum pause between two locks (``min_pause_min``).
    """

    category = "heat_pump"
    default_priority = 35
    fields = (
        *COMMON_FIELDS,
        FieldSpec(
            "control_entity",
            KIND_ENTITY,
            domains=(*ON_OFF_DOMAINS, *SELECT_DOMAINS, *NUMBER_DOMAINS, "climate"),
        ),
        FieldSpec("reduce_value", KIND_TEXT),
        FieldSpec("power_entity", KIND_ENTITY, required=True, domains=("sensor",)),
        FieldSpec(
            "run_threshold_w",
            KIND_NUMBER,
            default=300,
            minimum=10,
            maximum=20000,
            step=10,
            unit="W",
        ),
        FieldSpec("outdoor_temp_entity", KIND_ENTITY, domains=("sensor", "weather")),
        FieldSpec(
            "next_start_entity", KIND_ENTITY, domains=("sensor", "input_datetime")
        ),
        FieldSpec(
            "min_runtime_min",
            KIND_NUMBER,
            default=10,
            minimum=0,
            maximum=120,
            step=1,
            unit="min",
        ),
        FieldSpec(
            "max_block_min",
            KIND_NUMBER,
            default=30,
            minimum=1,
            maximum=120,
            step=1,
            unit="min",
        ),
        FieldSpec(
            "max_block_day_min",
            KIND_NUMBER,
            default=120,
            minimum=1,
            maximum=720,
            step=5,
            unit="min",
        ),
        FieldSpec(
            "min_pause_min",
            KIND_NUMBER,
            default=30,
            minimum=0,
            maximum=240,
            step=1,
            unit="min",
        ),
        FieldSpec("budget_reserve", KIND_BOOL, default=False),
    )

    def __init__(self, hass, config: dict[str, Any]) -> None:
        """Initialize."""
        super().__init__(hass, config)
        self.forecast = StartForecast()
        self.running = False
        self.run_started: datetime | None = None
        self._run_energy_kwh = 0.0
        self._last_update: datetime | None = None
        self.last_block_end: datetime | None = None
        self.blocked_today_s = 0.0
        self.blocked_day: str | None = None

    # -- helpers --------------------------------------------------------------

    def _cfg(self, key: str) -> float:
        default = next(f.default for f in self.fields if f.key == key)
        return float(self.config.get(key, default))

    def outdoor_temp(self) -> float | None:
        """Outdoor temperature from a sensor or weather entity."""
        entity = self.config.get("outdoor_temp_entity")
        if not entity:
            return None
        state = self.hass.states.get(entity)
        if state is None:
            return None
        if entity.startswith("weather."):
            value = state.attributes.get("temperature")
            return float(value) if value is not None else None
        return state_to_float(state)

    def external_start(self) -> datetime | None:
        """Externally provided next start time (takes precedence)."""
        entity = self.config.get("next_start_entity")
        if not entity:
            return None
        state = self.hass.states.get(entity)
        if state is None:
            return None
        parsed = dt_util.parse_datetime(state.state)
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.get_default_time_zone())
        return parsed

    def _roll_day(self, now: datetime) -> None:
        day = dt_util.as_local(now).date().isoformat()
        if day != self.blocked_day:
            self.blocked_day = day
            self.blocked_today_s = 0.0

    def blocked_today(self, now: datetime) -> float:
        """Seconds locked today including a running lock."""
        self._roll_day(now)
        current = (now - self.engaged_at).total_seconds() if self.engaged_at else 0.0
        return self.blocked_today_s + current

    # -- cycle ----------------------------------------------------------------

    def update(self, now: datetime) -> None:
        """Track runs and learn start statistics."""
        self._roll_day(now)
        local = dt_util.as_local(now)
        temp = self.outdoor_temp()
        self.forecast.observe_hour(local, temp)
        power = self.power_kw()
        if power is None:
            self._last_update = now
            return
        is_running = power * 1000 >= self._cfg("run_threshold_w")
        if self._last_update is not None and self.running:
            dt_s = min((now - self._last_update).total_seconds(), 60.0)
            self._run_energy_kwh += power * dt_s / 3600
        if is_running and not self.running:
            self.running = True
            self.run_started = now
            self._run_energy_kwh = 0.0
            # A start while locked by us is not a natural start; don't learn it.
            if not self.engaged:
                self.forecast.record_start(local, temp)
        elif not is_running and self.running:
            self.running = False
            if self.run_started is not None:
                runtime_s = (now - self.run_started).total_seconds()
                if runtime_s > 0:
                    self.forecast.record_run(
                        runtime_s, self._run_energy_kwh * 3600 / runtime_s
                    )
            self.run_started = None
        self._last_update = now

    def can_reduce(self, now: datetime) -> tuple[bool, str]:
        """Apply all protection times."""
        if not self.control_entity or self.config.get("reduce_value") in (None, ""):
            return False, "not_controllable"
        ok, reason = super().can_reduce(now)
        if not ok:
            return ok, reason
        if (
            self.running
            and self.run_started is not None
            and now - self.run_started < timedelta(minutes=self._cfg("min_runtime_min"))
        ):
            return False, "min_runtime"
        if self.blocked_today(now) >= self._cfg("max_block_day_min") * 60:
            return False, "max_block_per_day"
        if self.last_block_end is not None and now - self.last_block_end < timedelta(
            minutes=self._cfg("min_pause_min")
        ):
            return False, "min_pause"
        return True, "ok"

    def should_release(self, now: datetime) -> bool:
        """Release when the single lock or the daily lock budget is used up."""
        if self.engaged_at is None:
            return False
        if now - self.engaged_at >= timedelta(minutes=self._cfg("max_block_min")):
            return True
        return self.blocked_today(now) >= self._cfg("max_block_day_min") * 60

    def on_released(self, now: datetime) -> None:
        """Book the lock time."""
        if self.engaged_at is not None:
            self._roll_day(now)
            self.blocked_today_s += max((now - self.engaged_at).total_seconds(), 0.0)
        self.last_block_end = now

    def expected_extra_kw(self, now: datetime, window_end: datetime) -> float:
        """Budget reserve for an expected start within the window."""
        if not self.config.get("budget_reserve") or self.running or self.engaged:
            return 0.0
        return self.forecast.expected_extra_kw(
            dt_util.as_local(now),
            dt_util.as_local(window_end),
            self.outdoor_temp(),
            self.external_start(),
        )

    def next_start(self, now: datetime) -> tuple[datetime, float] | None:
        """Next expected start (external time has precedence)."""
        external = self.external_start()
        if external is not None and external >= now:
            return external, 1.0
        return self.forecast.next_expected_start(
            dt_util.as_local(now), self.outdoor_temp()
        )

    def start_probability(self, now: datetime) -> float:
        """Start probability for the current hour."""
        return self.forecast.probability(
            dt_util.as_local(now).hour, self.outdoor_temp()
        )

    # -- persistence ----------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Include protection bookkeeping."""
        data = super().snapshot()
        data.update(
            {
                "last_block_end": self.last_block_end.isoformat()
                if self.last_block_end
                else None,
                "blocked_today_s": self.blocked_today_s,
                "blocked_day": self.blocked_day,
            }
        )
        return data

    def load_snapshot(self, data: dict[str, Any]) -> None:
        """Restore protection bookkeeping."""
        super().load_snapshot(data)
        raw = data.get("last_block_end")
        self.last_block_end = datetime.fromisoformat(raw) if raw else None
        self.blocked_today_s = float(data.get("blocked_today_s", 0.0))
        self.blocked_day = data.get("blocked_day")

    def learning_data(self) -> dict[str, Any]:
        """Forecast statistics."""
        return self.forecast.as_dict()

    def load_learning_data(self, data: dict[str, Any] | None) -> None:
        """Restore forecast statistics."""
        self.forecast = StartForecast.from_dict(data)

    def diagnostics(self) -> dict[str, Any]:
        """Add learning information."""
        data = super().diagnostics()
        data.update(
            {
                "running": self.running,
                "blocked_today_s": self.blocked_today_s,
                "typical_kw": self.forecast.typical_kw,
                "typical_runtime_s": self.forecast.typical_runtime_s,
            }
        )
        return data
