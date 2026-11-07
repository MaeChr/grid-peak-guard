"""Binary sensors for Grid Peak Guard."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GridPeakGuardConfigEntry
from .coordinator import GridPeakGuardCoordinator
from .entity import GridPeakGuardEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GridPeakGuardConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [LimitAtRiskSensor(coordinator), InterventionActiveSensor(coordinator)]
    )


class LimitAtRiskSensor(GridPeakGuardEntity, BinarySensorEntity):
    """On while the projection exceeds the effective limit."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: GridPeakGuardCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "limit_at_risk")

    @property
    def is_on(self) -> bool:
        """Return true if the limit is at risk."""
        data = self.coordinator.data
        return data.projected_kw > data.limit_kw


class InterventionActiveSensor(GridPeakGuardEntity, BinarySensorEntity):
    """On while at least one device is reduced (or simulated as reduced)."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: GridPeakGuardCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "intervention_active")

    @property
    def is_on(self) -> bool:
        """Return true if any device is engaged."""
        return bool(self.coordinator.data.engaged)

    @property
    def extra_state_attributes(self) -> dict:
        """Return engaged devices."""
        return {
            "devices": self.coordinator.data.engaged,
            "simulation": self.coordinator.data.simulation,
        }
