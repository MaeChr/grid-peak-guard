"""Base entity for Grid Peak Guard."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GridPeakGuardCoordinator


class GridPeakGuardEntity(CoordinatorEntity[GridPeakGuardCoordinator]):
    """Common entity attributes."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GridPeakGuardCoordinator, key: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Grid Peak Guard",
            model="Peak limiter",
        )
