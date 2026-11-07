"""Household appliance: only delay the start, never interrupt a running program."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .base import (
    COMMON_FIELDS,
    KIND_ENTITY,
    KIND_NUMBER,
    ON_OFF_DOMAINS,
    BaseDevice,
    FieldSpec,
    register,
)


@register
class ApplianceDevice(BaseDevice):
    """Appliance behind a smart plug or a "start allowed" switch.

    The control entity is only switched off when the appliance has been idle
    (power at or below ``standby_w``) for at least ``idle_min`` minutes, so a
    running program, including low-power phases, is never interrupted.
    """

    category = "appliance"
    default_priority = 30
    fields = (
        *COMMON_FIELDS,
        FieldSpec("control_entity", KIND_ENTITY, required=True, domains=ON_OFF_DOMAINS),
        FieldSpec("power_entity", KIND_ENTITY, required=True, domains=("sensor",)),
        FieldSpec(
            "standby_w",
            KIND_NUMBER,
            default=5,
            minimum=0,
            maximum=200,
            step=1,
            unit="W",
        ),
        FieldSpec(
            "idle_min",
            KIND_NUMBER,
            default=10,
            minimum=1,
            maximum=120,
            step=1,
            unit="min",
        ),
        FieldSpec(
            "max_delay_min",
            KIND_NUMBER,
            default=60,
            minimum=1,
            maximum=480,
            step=5,
            unit="min",
        ),
    )

    def __init__(self, hass, config: dict[str, Any]) -> None:
        """Initialize."""
        super().__init__(hass, config)
        self.idle_since: datetime | None = None

    def reduce_value(self) -> str:
        """Start is blocked by switching off."""
        return "off"

    def update(self, now: datetime) -> None:
        """Track how long the appliance has been idle."""
        power = self.power_kw()
        if power is None or power * 1000 > float(self.config.get("standby_w", 5)):
            self.idle_since = None
        elif self.idle_since is None:
            self.idle_since = now

    def can_reduce(self, now: datetime) -> tuple[bool, str]:
        """Only block an idle appliance."""
        ok, reason = super().can_reduce(now)
        if not ok:
            return ok, reason
        assert self.control_entity is not None
        if self.hass.states.get(self.control_entity).state != "on":
            return False, "already_off"
        if self.idle_since is None:
            return False, "running"
        if now - self.idle_since < timedelta(
            minutes=float(self.config.get("idle_min", 10))
        ):
            return False, "not_idle_long_enough"
        return True, "ok"

    def should_release(self, now: datetime) -> bool:
        """Release after the maximum delay."""
        if self.engaged_at is None:
            return False
        return now - self.engaged_at >= timedelta(
            minutes=float(self.config.get("max_delay_min", 60))
        )
