"""Consistency of profiles, device modules and translations."""

import json
from pathlib import Path
import re

from custom_components.grid_peak_guard.devices import CATEGORIES, DEVICE_REGISTRY
from custom_components.grid_peak_guard.profile_loader import load_profiles_sync

COMPONENT = Path(__file__).parent.parent / "custom_components" / "grid_peak_guard"


def _keys(obj, prefix=""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from _keys(value, f"{prefix}{key}.")
    else:
        yield prefix.rstrip(".")


def test_registry_matches_categories() -> None:
    assert set(DEVICE_REGISTRY) == set(CATEGORIES)
    for cat in CATEGORIES:
        assert (COMPONENT / "profiles" / cat).is_dir()


def test_profiles_valid() -> None:
    profiles = load_profiles_sync()
    assert set(profiles) == set(CATEGORIES)
    for category, by_id in profiles.items():
        field_keys = {f.key for f in DEVICE_REGISTRY[category].fields}
        for profile in by_id.values():
            assert set(profile.defaults) <= field_keys, profile.id
            assert set(profile.suggestions) <= field_keys, profile.id
            for pattern in profile.suggestions.values():
                re.compile(pattern)
    # Every JSON file was loaded (none silently skipped)
    files = list((COMPONENT / "profiles").glob("*/*.json"))
    assert len(files) == sum(len(p) for p in profiles.values())


def test_translations_complete() -> None:
    strings = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
    reference = set(_keys(strings))
    for path in (COMPONENT / "translations").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert set(_keys(data)) == reference, path.name


def test_every_device_field_translated() -> None:
    strings = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
    labels = strings["options"]["step"]["device"]["data"]
    for cls in DEVICE_REGISTRY.values():
        for spec in cls.fields:
            assert spec.key in labels, spec.key
    assert set(strings["selector"]["category"]["options"]) == set(CATEGORIES)


def test_no_personal_entity_ids_in_profiles() -> None:
    """Profiles contain regex hints only, never complete entity IDs."""
    for path in (COMPONENT / "profiles").glob("*/*.json"):
        raw = json.loads(path.read_text(encoding="utf-8"))
        for value in raw.get("defaults", {}).values():
            assert not re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", str(value)), path
