"""Device model profiles (JSON) with defaults and entity suggestions."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import re
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PROFILES_DIR = Path(__file__).parent / "profiles"
GENERIC_PROFILE = "generic"
_DATA_KEY = f"{DOMAIN}_profiles"


@dataclass(frozen=True, slots=True)
class Profile:
    """A device model profile."""

    id: str
    name: str
    category: str
    defaults: dict[str, Any] = field(default_factory=dict)
    suggestions: dict[str, str] = field(default_factory=dict)
    notes: str = ""


def load_profiles_sync(base: Path = PROFILES_DIR) -> dict[str, dict[str, Profile]]:
    """Read all profiles from disk (blocking; run in the executor)."""
    result: dict[str, dict[str, Profile]] = {}
    for path in sorted(base.glob("*/*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            profile = Profile(
                id=raw["id"],
                name=raw["name"],
                category=raw["category"],
                defaults=dict(raw.get("defaults", {})),
                suggestions=dict(raw.get("suggestions", {})),
                notes=raw.get("notes", ""),
            )
        except (OSError, ValueError, KeyError) as err:
            _LOGGER.warning("Invalid profile %s: %s", path, err)
            continue
        if profile.category != path.parent.name:
            _LOGGER.warning("Profile %s is in the wrong folder", path)
            continue
        result.setdefault(profile.category, {})[profile.id] = profile
    return result


async def async_get_profiles(hass: HomeAssistant) -> dict[str, dict[str, Profile]]:
    """Return cached profiles, loading them in the executor once."""
    if _DATA_KEY not in hass.data:
        hass.data[_DATA_KEY] = await hass.async_add_executor_job(load_profiles_sync)
    return hass.data[_DATA_KEY]


def suggest_entities(
    hass: HomeAssistant, profile: Profile, domains_by_field: dict[str, tuple[str, ...]]
) -> dict[str, str]:
    """Return the first matching entity per field for the profile's regexes."""
    found: dict[str, str] = {}
    for key, pattern in profile.suggestions.items():
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            _LOGGER.warning("Invalid regex in profile %s: %s", profile.id, pattern)
            continue
        domains = domains_by_field.get(key) or ()
        for entity_id in sorted(hass.states.async_entity_ids(domains or None)):
            if regex.search(entity_id):
                found[key] = entity_id
                break
    return found
