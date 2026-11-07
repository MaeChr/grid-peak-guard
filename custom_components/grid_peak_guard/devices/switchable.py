"""Load on a switch or smart plug, switched off for a limited time."""

from __future__ import annotations

from datetime import datetime, timedelta

from .base import (
    COMMON_FIELDS,
    KIND_ENTITY,
    KIND_NUMBER,
    ON_OFF_DOMAINS,
    POWER_FIELD,
    BaseDevice,
    FieldSpec,
    register,
)


@register
class SwitchableDevice(BaseDevice):
    """Load on a switch/smart plug that may be switched off for a limited time."""

    category = "switchable"
    default_priority = 30
    fields = (
        *COMMON_FIELDS,
        FieldSpec("control_entity", KIND_ENTITY, required=True, domains=ON_OFF_DOMAINS),
        POWER_FIELD,
        FieldSpec(
            "min_power_w",
            KIND_NUMBER,
            default=50,
            minimum=0,
            maximum=50000,
            step=10,
            unit="W",
        ),
        FieldSpec(
            "max_off_min",
            KIND_NUMBER,
            default=15,
            minimum=1,
            maximum=240,
            step=1,
            unit="min",
        ),
    )

    def reduce_value(self) -> str:
        """Switchable loads are always switched off."""
        return "off"

    def can_reduce(self, now: datetime) -> tuple[bool, str]:
        """Only switch off what is on and actually consuming."""
        ok, reason = super().can_reduce(now)
        if not ok:
            return ok, reason
        assert self.control_entity is not None
        state = self.hass.states.get(self.control_entity)
        if state is None or state.state != "on":
            return False, "already_off"
        power = self.power_kw()
        if power is not None and power * 1000 < float(
            self.config.get("min_power_w", 50)
        ):
            return False, "not_consuming"
        return True, "ok"

    def should_release(self, now: datetime) -> bool:
        """Release after the maximum off time."""
        if self.engaged_at is None:
            return False
        limit = timedelta(minutes=float(self.config.get("max_off_min", 15)))
        return now - self.engaged_at >= limit
