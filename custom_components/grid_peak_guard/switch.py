"""Switches for Grid Peak Guard (control enabled, simulation mode)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
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
    """Set up switches."""
    coordinator = entry.runtime_data
    async_add_entities([ControlSwitch(coordinator), SimulationSwitch(coordinator)])


class ControlSwitch(GridPeakGuardEntity, SwitchEntity):
    """Enable or disable control. Turning off restores all devices."""

    def __init__(self, coordinator: GridPeakGuardCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "control")

    @property
    def is_on(self) -> bool:
        """Return true if control is enabled."""
        return self.coordinator.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable control."""
        await self.coordinator.async_set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable control and restore devices."""
        await self.coordinator.async_set_enabled(False)


class SimulationSwitch(GridPeakGuardEntity, SwitchEntity):
    """Simulation mode: decisions are logged and fired as events only."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: GridPeakGuardCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator, "simulation")

    @property
    def is_on(self) -> bool:
        """Return true if simulation mode is active."""
        return self.coordinator.simulation

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable simulation mode."""
        await self.coordinator.async_set_simulation(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable simulation mode (real control)."""
        await self.coordinator.async_set_simulation(False)
