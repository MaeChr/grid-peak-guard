"""Sensors for Grid Peak Guard."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import GridPeakGuardConfigEntry
from .coordinator import GridPeakGuardCoordinator, GuardData
from .devices.heat_pump import HeatPumpDevice
from .entity import GridPeakGuardEntity


@dataclass(frozen=True, kw_only=True)
class GuardSensorDescription(SensorEntityDescription):
    """Sensor description with a value function."""

    value_fn: Callable[[GuardData], Any]
    attrs_fn: Callable[[GuardData], dict[str, Any]] | None = None


def _power(
    key: str, fn: Callable[[GuardData], Any], **kw: Any
) -> GuardSensorDescription:
    return GuardSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=fn,
        **kw,
    )


SENSORS: tuple[GuardSensorDescription, ...] = (
    _power(
        "projected_power",
        lambda d: d.projected_kw,
        attrs_fn=lambda d: {
            "window_start": d.window_start.isoformat(),
            "window_end": d.window_end.isoformat(),
            "expected_extra_kw": round(d.extra_kw, 3),
            "reason": d.reason,
            "engaged": d.engaged,
            "simulation": d.simulation,
        },
    ),
    _power("window_average", lambda d: d.average_kw),
    _power("effective_limit", lambda d: d.limit_kw),
    _power("required_reduction", lambda d: d.required_reduction_kw),
    _power("month_peak", lambda d: d.month_peak_kw),
    _power("last_window_average", lambda d: d.last_window_kw),
    GuardSensorDescription(
        key="window_energy",
        translation_key="window_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=3,
        value_fn=lambda d: d.energy_kwh,
        attrs_fn=lambda d: {"window_complete": d.window_complete},
    ),
    GuardSensorDescription(
        key="escalation_level",
        translation_key="escalation_level",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.level,
        attrs_fn=lambda d: {"max_level": d.max_level},
    ),
    GuardSensorDescription(
        key="monthly_power_cost",
        translation_key="monthly_power_cost",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        value_fn=lambda d: d.power_cost,
    ),
    GuardSensorDescription(
        key="monthly_cost_estimate",
        translation_key="monthly_cost_estimate",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        value_fn=lambda d: d.month_cost,
        attrs_fn=lambda d: {"month_energy_kwh": round(d.month_energy_kwh, 3)},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GridPeakGuardConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    currency = hass.config.currency
    entities: list[SensorEntity] = [
        GuardSensor(coordinator, desc, currency) for desc in SENSORS
    ]
    for device in coordinator.devices:
        if isinstance(device, HeatPumpDevice):
            entities.append(HeatPumpNextStartSensor(coordinator, device))
            entities.append(HeatPumpProbabilitySensor(coordinator, device))
    async_add_entities(entities)


class GuardSensor(GridPeakGuardEntity, SensorEntity):
    """Coordinator value sensor."""

    entity_description: GuardSensorDescription

    def __init__(
        self,
        coordinator: GridPeakGuardCoordinator,
        description: GuardSensorDescription,
        currency: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        if description.device_class == SensorDeviceClass.MONETARY:
            self._attr_native_unit_of_measurement = currency

    @property
    def native_value(self) -> Any:
        """Return the value."""
        value = self.entity_description.value_fn(self.coordinator.data)
        return round(value, 4) if isinstance(value, float) else value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return attributes."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)


class _HeatPumpSensor(GridPeakGuardEntity, SensorEntity):
    def __init__(
        self, coordinator: GridPeakGuardCoordinator, device: HeatPumpDevice, key: str
    ) -> None:
        super().__init__(coordinator, key)
        self.device = device
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{device.device_id}_{key}"
        )
        self._attr_translation_placeholders = {"device": device.name}


class HeatPumpNextStartSensor(_HeatPumpSensor):
    """Next expected heat pump start."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self, coordinator: GridPeakGuardCoordinator, device: HeatPumpDevice
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, device, "heat_pump_next_start")

    @property
    def native_value(self) -> datetime | None:
        """Return the next expected start."""
        nxt = self.device.next_start(dt_util.utcnow())
        return nxt[0] if nxt else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return learning information."""
        nxt = self.device.next_start(dt_util.utcnow())
        fc = self.device.forecast
        return {
            "probability": round(nxt[1], 3) if nxt else None,
            "typical_power_kw": round(fc.typical_kw, 3) if fc.typical_kw else None,
            "typical_runtime_min": round(fc.typical_runtime_s / 60, 1)
            if fc.typical_runtime_s
            else None,
            "running": self.device.running,
            "locked": self.device.engaged,
        }


class HeatPumpProbabilitySensor(_HeatPumpSensor):
    """Start probability in the current hour."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: GridPeakGuardCoordinator, device: HeatPumpDevice
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, device, "heat_pump_start_probability")

    @property
    def native_value(self) -> float:
        """Return the probability in percent."""
        return round(self.device.start_probability(dt_util.utcnow()) * 100, 1)
