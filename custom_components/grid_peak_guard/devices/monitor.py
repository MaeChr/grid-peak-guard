"""Monitored load without control (for display and diagnostics only)."""

from __future__ import annotations

from .base import COMMON_FIELDS, KIND_ENTITY, BaseDevice, FieldSpec, register


@register
class MonitorDevice(BaseDevice):
    """Only measures power; never controlled."""

    category = "monitor"
    default_priority = 99
    controllable = False
    fields = (
        *COMMON_FIELDS,
        FieldSpec("power_entity", KIND_ENTITY, required=True, domains=("sensor",)),
    )
