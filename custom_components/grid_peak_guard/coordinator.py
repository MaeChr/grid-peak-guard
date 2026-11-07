"""Coordinator: measuring window, projection, escalation and restore."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import logic
from .const import (
    CONF_DEVICES,
    CONF_ENERGY_PRICE,
    CONF_ESCALATION_WAIT_S,
    CONF_GRID_ENERGY_PRICE,
    CONF_GRID_POWER_ENTITY,
    CONF_HARD_MARGIN_KW,
    CONF_IMPORT_ENERGY_ENTITY,
    CONF_INVERT_GRID_POWER,
    CONF_MINIMUM_KW,
    CONF_POWER_FACTOR_ABOVE,
    CONF_POWER_PRICE,
    CONF_POWER_THRESHOLD_KW,
    CONF_PRICE_ENTITY,
    CONF_SETTLE_S,
    CONF_SIMULATION,
    CONF_TARGET_KW,
    CONF_UPDATE_INTERVAL_S,
    CONF_USE_MONTH_PEAK,
    CONF_WINDOW_MINUTES,
    DEFAULT_ESCALATION_WAIT_S,
    DEFAULT_HARD_MARGIN_KW,
    DEFAULT_MINIMUM_KW,
    DEFAULT_POWER_FACTOR_ABOVE,
    DEFAULT_POWER_THRESHOLD_KW,
    DEFAULT_SETTLE_S,
    DEFAULT_TARGET_KW,
    DEFAULT_UPDATE_INTERVAL_S,
    DEFAULT_WINDOW_MINUTES,
    DOMAIN,
    MAX_INTEGRATION_GAP_S,
    STORAGE_VERSION,
)
from .devices import BaseDevice, create_device
from .devices.base import state_to_float, state_to_kw

_LOGGER = logging.getLogger(__name__)

SAVE_DELAY_S = 60


@dataclass
class GuardData:
    """Snapshot of the current state for entities."""

    window_start: datetime
    window_end: datetime
    energy_kwh: float = 0.0
    current_kw: float | None = None
    average_kw: float = 0.0
    projected_kw: float = 0.0
    extra_kw: float = 0.0
    limit_kw: float = 0.0
    hard_limit_kw: float = 0.0
    required_reduction_kw: float = 0.0
    level: int = 0
    max_level: int = 0
    reason: str = logic.REASON_IDLE
    window_complete: bool = False
    last_window_kw: float | None = None
    month_peak_kw: float = 0.0
    month_energy_kwh: float = 0.0
    power_cost: float = 0.0
    month_cost: float = 0.0
    engaged: list[str] = field(default_factory=list)
    enabled: bool = True
    simulation: bool = True


def _energy_to_kwh(state) -> float | None:
    value = state_to_float(state)
    if value is None:
        return None
    unit = state.attributes.get("unit_of_measurement")
    if unit == UnitOfEnergy.WATT_HOUR:
        return value / 1000.0
    if unit == UnitOfEnergy.MEGA_WATT_HOUR:
        return value * 1000.0
    return value


class GridPeakGuardCoordinator(DataUpdateCoordinator[GuardData]):
    """Keeps the averaged grid import per window below the effective limit."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.conf: dict[str, Any] = {**entry.data, **entry.options}
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=int(
                    self.conf.get(CONF_UPDATE_INTERVAL_S, DEFAULT_UPDATE_INTERVAL_S)
                )
            ),
        )
        self.store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self.devices: list[BaseDevice] = [
            create_device(hass, cfg) for cfg in self.conf.get(CONF_DEVICES, [])
        ]
        self.window_minutes = int(
            self.conf.get(CONF_WINDOW_MINUTES, DEFAULT_WINDOW_MINUTES)
        )
        self.enabled = True
        # Set on unload/reload so no cycle can engage devices after the
        # final restore.
        self.shutting_down = False
        self.simulation = bool(self.conf.get(CONF_SIMULATION, True))
        # Window state
        self._window_start: datetime | None = None
        self._energy_kwh = 0.0
        self._meter_start: float | None = None
        self._window_complete = False
        self._last_sample: tuple[datetime, float] | None = None
        self._last_window_kw: float | None = None
        # Month state
        self._month: str | None = None
        self._month_peak_kw = 0.0
        self._month_energy_kwh = 0.0
        # Escalation state: devices engaged in the current window. A device
        # released early (protection limit) is not engaged again in the same
        # window; a device that refused (e.g. minimum runtime) is retried.
        self._used: set[str] = set()
        self._last_change: datetime | None = None
        self._reason = logic.REASON_IDLE

    # -- helpers --------------------------------------------------------------

    def _f(self, key: str, default: float) -> float:
        value = self.conf.get(key)
        return float(default if value is None else value)

    @property
    def control_order(self) -> list[BaseDevice]:
        """Controllable devices in escalation order."""
        return sorted(
            (d for d in self.devices if d.controllable),
            key=lambda d: (d.priority, d.name),
        )

    def _grid_kw(self) -> float | None:
        kw = state_to_kw(self.hass.states.get(self.conf[CONF_GRID_POWER_ENTITY]))
        if kw is None:
            return None
        if self.conf.get(CONF_INVERT_GRID_POWER):
            kw = -kw
        return max(kw, 0.0)  # only import counts

    def _meter_kwh(self) -> float | None:
        entity = self.conf.get(CONF_IMPORT_ENERGY_ENTITY)
        if not entity:
            return None
        return _energy_to_kwh(self.hass.states.get(entity))

    def _month_key(self, now: datetime) -> str:
        return dt_util.as_local(now).strftime("%Y-%m")

    # -- persistence ------------------------------------------------------------

    async def async_load(self) -> None:
        """Load persisted state and schedule restores of interrupted interventions."""
        data = await self.store.async_load() or {}
        self._month = data.get("month")
        self._month_peak_kw = float(data.get("month_peak_kw", 0.0))
        self._month_energy_kwh = float(data.get("month_energy_kwh", 0.0))
        self._last_window_kw = data.get("last_window_kw")
        self.enabled = bool(data.get("enabled", True))
        self.simulation = bool(data.get("simulation", self.simulation))
        window = data.get("window") or {}
        if window.get("start"):
            self._window_start = datetime.fromisoformat(window["start"])
            self._energy_kwh = float(window.get("energy_kwh", 0.0))
            self._meter_start = window.get("meter_start")
            self._window_complete = bool(window.get("complete", False))
            if window.get("last_sample_at") is not None:
                self._last_sample = (
                    datetime.fromisoformat(window["last_sample_at"]),
                    float(window.get("last_sample_kw", 0.0)),
                )
        snapshots = data.get("devices", {})
        learning = data.get("learning", {})
        for device in self.devices:
            device.load_learning_data(learning.get(device.device_id))
            if device.device_id in snapshots:
                device.load_snapshot(snapshots[device.device_id])
        # Interventions that survived a restart are restored right away.
        await self._async_restore_all(dt_util.utcnow())

    def _store_data(self) -> dict[str, Any]:
        last = self._last_sample
        return {
            "month": self._month,
            "month_peak_kw": self._month_peak_kw,
            "month_energy_kwh": self._month_energy_kwh,
            "last_window_kw": self._last_window_kw,
            "enabled": self.enabled,
            "simulation": self.simulation,
            "window": {
                "start": self._window_start.isoformat() if self._window_start else None,
                "energy_kwh": self._energy_kwh,
                "meter_start": self._meter_start,
                "complete": self._window_complete,
                "last_sample_at": last[0].isoformat() if last else None,
                "last_sample_kw": last[1] if last else None,
            },
            "devices": {d.device_id: d.snapshot() for d in self.devices},
            "learning": {
                d.device_id: data
                for d in self.devices
                if (data := d.learning_data()) is not None
            },
        }

    async def async_save_now(self) -> None:
        """Persist immediately (used whenever interventions change)."""
        await self.store.async_save(self._store_data())

    # -- public controls ----------------------------------------------------------

    async def async_set_enabled(self, enabled: bool) -> None:
        """Enable/disable control; disabling restores everything."""
        self.enabled = enabled
        if not enabled:
            await self._async_restore_all(dt_util.utcnow())
        await self.async_save_now()
        await self.async_refresh()

    async def async_set_simulation(self, simulation: bool) -> None:
        """Switch simulation mode; open interventions are restored first."""
        await self._async_restore_all(dt_util.utcnow())
        self.simulation = simulation
        await self.async_save_now()
        await self.async_refresh()

    async def async_shutdown_restore(self) -> None:
        """Restore everything (unload)."""
        self.shutting_down = True
        await self._async_restore_all(dt_util.utcnow())
        await self.async_save_now()

    # -- cycle ------------------------------------------------------------------

    async def _async_restore_all(self, now: datetime) -> bool:
        changed = False
        for device in self.devices:
            if device.engaged:
                await device.async_restore(now)
                changed = True
        self._used.clear()
        self._last_change = now
        if changed:
            await self.async_save_now()
        return changed

    def _finish_window(self, now: datetime) -> None:
        assert self._window_start is not None
        window_s = self.window_minutes * 60
        average = self._energy_kwh * logic.SECONDS_PER_HOUR / window_s
        self._last_window_kw = average
        month = self._month_key(self._window_start)
        if month != self._month:
            self._month = month
            self._month_peak_kw = 0.0
            self._month_energy_kwh = 0.0
        self._month_energy_kwh += self._energy_kwh
        if self._window_complete:
            self._month_peak_kw = max(self._month_peak_kw, average)

    def _start_window(
        self, start: datetime, now: datetime, meter: float | None
    ) -> None:
        self._window_start = start
        self._energy_kwh = 0.0
        self._meter_start = meter
        tolerance = 2 * self.update_interval.total_seconds()
        self._window_complete = (now - start).total_seconds() <= tolerance

    def _integrate(
        self, now: datetime, grid_kw: float | None, meter: float | None
    ) -> None:
        if meter is not None and self._meter_start is not None:
            self._energy_kwh = max(meter - self._meter_start, 0.0)
        elif self._last_sample is not None:
            last_at, last_kw = self._last_sample
            dt_s = (now - last_at).total_seconds()
            if dt_s > MAX_INTEGRATION_GAP_S:
                self._window_complete = False
            elif dt_s > 0:
                self._energy_kwh += last_kw * dt_s / logic.SECONDS_PER_HOUR
        if meter is not None and self._meter_start is None:
            self._meter_start = meter
            self._window_complete = False
        if grid_kw is not None:
            self._last_sample = (now, grid_kw)

    async def _async_update_data(self) -> GuardData:
        return await self.async_cycle(dt_util.utcnow())

    async def async_cycle(self, now: datetime) -> GuardData:
        """Run one control cycle (public for tests)."""
        start, end = logic.window_bounds(now, self.window_minutes)
        grid_kw = self._grid_kw()
        meter = self._meter_kwh()
        changed = False

        # Window change: finish, restore, start new.
        if self._window_start is None or self._window_start != start:
            if self._window_start is not None and self._window_start < start:
                # Close the previous window up to its end.
                prev_end = self._window_start + timedelta(minutes=self.window_minutes)
                self._integrate(min(now, prev_end), None, meter)
                self._finish_window(now)
            changed |= await self._async_restore_all(now)
            last = self._last_sample
            self._start_window(start, now, meter)
            if last is not None:
                self._last_sample = (max(last[0], start), last[1])
        self._integrate(now, grid_kw, meter)

        for device in self.devices:
            device.update(now)

        # Retry failed restores and honour device protection limits.
        for device in self.devices:
            if device.engaged and (
                device.last_reason == "restore_failed" or device.should_release(now)
            ):
                await device.async_restore(now)
                changed = True

        window_s = self.window_minutes * 60
        elapsed_s = (now - start).total_seconds()
        remaining_s = max((end - now).total_seconds(), 0.0)
        extra_kw = sum(
            d.expected_extra_kw(now, end) for d in self.devices if not d.engaged
        )
        current = grid_kw if grid_kw is not None else 0.0
        projected = logic.projected_average_kw(
            self._energy_kwh, current, extra_kw, remaining_s, window_s
        )
        limit = logic.effective_limit_kw(
            self._f(CONF_TARGET_KW, DEFAULT_TARGET_KW),
            self._f(CONF_MINIMUM_KW, DEFAULT_MINIMUM_KW),
            self._month_peak_kw if self._month == self._month_key(now) else 0.0,
            bool(self.conf.get(CONF_USE_MONTH_PEAK, True)),
        )
        hard_limit = limit + self._f(CONF_HARD_MARGIN_KW, DEFAULT_HARD_MARGIN_KW)
        order = self.control_order

        if self.shutting_down:
            self._reason = "shutting_down"
        elif self.enabled and grid_kw is not None:
            since = (
                (now - self._last_change).total_seconds()
                if self._last_change
                else float("inf")
            )
            decision = logic.next_escalation(
                projected_kw=projected,
                limit_kw=limit,
                hard_limit_kw=hard_limit,
                current_level=len(self._used),
                max_level=len(order),
                elapsed_s=elapsed_s,
                settle_s=self._f(CONF_SETTLE_S, DEFAULT_SETTLE_S),
                seconds_since_change=since,
                wait_s=self._f(CONF_ESCALATION_WAIT_S, DEFAULT_ESCALATION_WAIT_S),
            )
            self._reason = decision.reason
            if decision.level > len(self._used):
                all_at_once = decision.reason == logic.REASON_HARD_LIMIT
                changed |= await self._async_escalate(order, now, all_at_once)
        elif not self.enabled:
            self._reason = "disabled"
        else:
            self._reason = "no_measurement"

        if changed:
            await self.async_save_now()
        else:
            self.store.async_delay_save(self._store_data, SAVE_DELAY_S)

        return self._build_data(
            start,
            end,
            grid_kw,
            extra_kw,
            projected,
            limit,
            hard_limit,
            remaining_s,
            elapsed_s,
        )

    async def _async_escalate(
        self, order: list[BaseDevice], now: datetime, all_at_once: bool
    ) -> bool:
        """Engage the next possible device (or all remaining at the hard limit).

        Devices that refuse now (protection times, not consuming) are skipped
        but not consumed, so they are tried again at the next stage.
        """
        changed = False
        for device in order:
            if device.device_id in self._used or device.engaged:
                continue
            engaged = await device.async_reduce(now, self.simulation)
            if device.engaged:  # also true for a failed call (snapshot kept)
                self._used.add(device.device_id)
                changed = True
            if engaged:
                self._last_change = now
                if not all_at_once:
                    break
        return changed

    def _build_data(
        self,
        start: datetime,
        end: datetime,
        grid_kw: float | None,
        extra_kw: float,
        projected: float,
        limit: float,
        hard_limit: float,
        remaining_s: float,
        elapsed_s: float,
    ) -> GuardData:
        window_s = self.window_minutes * 60
        same_month = self._month == self._month_key(start)
        peak = self._month_peak_kw if same_month else 0.0
        month_energy = (
            self._month_energy_kwh if same_month else 0.0
        ) + self._energy_kwh
        minimum = self._f(CONF_MINIMUM_KW, DEFAULT_MINIMUM_KW)
        power_cost = logic.monthly_power_cost(
            peak,
            self._f(CONF_POWER_PRICE, 0.0),
            minimum,
            self._f(CONF_POWER_THRESHOLD_KW, DEFAULT_POWER_THRESHOLD_KW),
            self._f(CONF_POWER_FACTOR_ABOVE, DEFAULT_POWER_FACTOR_ABOVE),
        )
        energy_price = self._f(CONF_ENERGY_PRICE, 0.0)
        price_entity = self.conf.get(CONF_PRICE_ENTITY)
        if price_entity:
            value = state_to_float(self.hass.states.get(price_entity))
            if value is not None:
                energy_price = value
        month_cost = power_cost + month_energy * (
            energy_price + self._f(CONF_GRID_ENERGY_PRICE, 0.0)
        )
        return GuardData(
            window_start=start,
            window_end=end,
            energy_kwh=self._energy_kwh,
            current_kw=grid_kw,
            average_kw=(
                self._energy_kwh * logic.SECONDS_PER_HOUR / elapsed_s
                if elapsed_s > 0
                else 0.0
            ),
            projected_kw=projected,
            extra_kw=extra_kw,
            limit_kw=limit,
            hard_limit_kw=hard_limit,
            required_reduction_kw=logic.required_reduction_kw(
                self._energy_kwh, grid_kw or 0.0, extra_kw, remaining_s, window_s, limit
            ),
            level=sum(1 for d in self.devices if d.engaged),
            max_level=len(self.control_order),
            reason=self._reason,
            window_complete=self._window_complete,
            last_window_kw=self._last_window_kw,
            month_peak_kw=peak,
            month_energy_kwh=month_energy,
            power_cost=power_cost,
            month_cost=month_cost,
            engaged=[d.name for d in self.devices if d.engaged],
            enabled=self.enabled,
            simulation=self.simulation,
        )
