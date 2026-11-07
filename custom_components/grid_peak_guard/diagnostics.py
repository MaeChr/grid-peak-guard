"""Diagnostics for Grid Peak Guard."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import GridPeakGuardConfigEntry

# Entity IDs can reveal names of rooms or people; redact them.
TO_REDACT = {
    "grid_power_entity",
    "import_energy_entity",
    "price_entity",
    "control_entity",
    "power_entity",
    "soc_entity",
    "outdoor_temp_entity",
    "next_start_entity",
    "entity_id",
    "name",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GridPeakGuardConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = asdict(coordinator.data) if coordinator.data else {}
    data.pop("engaged", None)
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "state": data,
        "devices": [d.diagnostics() for d in coordinator.devices],
    }
