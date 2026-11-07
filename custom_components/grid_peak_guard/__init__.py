"""Grid Peak Guard: keep the averaged grid import per window below a target."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import GridPeakGuardCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]

type GridPeakGuardConfigEntry = ConfigEntry[GridPeakGuardCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: GridPeakGuardConfigEntry
) -> bool:
    """Set up Grid Peak Guard from a config entry."""
    coordinator = GridPeakGuardCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: GridPeakGuardConfigEntry
) -> bool:
    """Unload a config entry; all interventions are restored first."""
    await entry.runtime_data.async_shutdown_restore()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: GridPeakGuardConfigEntry
) -> None:
    """Reload after options changed."""
    await hass.config_entries.async_reload(entry.entry_id)
