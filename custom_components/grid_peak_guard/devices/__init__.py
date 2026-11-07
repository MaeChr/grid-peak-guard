"""Device categories. Importing this package registers all categories."""

from __future__ import annotations

from . import (  # noqa: F401  (imported for registration)
    appliance,
    battery,
    heat_pump,
    modulating,
    monitor,
    switchable,
    wallbox,
)
from .base import DEVICE_REGISTRY, BaseDevice, FieldSpec, create_device

CATEGORIES: tuple[str, ...] = (
    "battery",
    "wallbox",
    "modulating",
    "switchable",
    "heat_pump",
    "appliance",
    "monitor",
)

__all__ = ["CATEGORIES", "DEVICE_REGISTRY", "BaseDevice", "FieldSpec", "create_device"]
