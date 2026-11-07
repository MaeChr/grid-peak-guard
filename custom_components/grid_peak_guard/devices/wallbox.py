"""EV charger: reduce charging current or pause."""

from __future__ import annotations

from datetime import datetime

from .base import (
    COMMON_FIELDS,
    KIND_ENTITY,
    KIND_NUMBER,
    KIND_TEXT,
    NUMBER_DOMAINS,
    ON_OFF_DOMAINS,
    POWER_FIELD,
    SELECT_DOMAINS,
    BaseDevice,
    FieldSpec,
    register,
)


@register
class WallboxDevice(BaseDevice):
    """EV charger: reduce charging current or pause."""

    category = "wallbox"
    default_priority = 20
    fields = (
        *COMMON_FIELDS,
        FieldSpec(
            "control_entity",
            KIND_ENTITY,
            required=True,
            domains=(*NUMBER_DOMAINS, *SELECT_DOMAINS, *ON_OFF_DOMAINS),
        ),
        FieldSpec("reduce_value", KIND_TEXT, required=True),
        POWER_FIELD,
        FieldSpec(
            "min_power_w",
            KIND_NUMBER,
            default=500,
            minimum=0,
            maximum=50000,
            step=50,
            unit="W",
        ),
    )

    def can_reduce(self, now: datetime) -> tuple[bool, str]:
        """Only engage while actually charging (if a power sensor exists)."""
        ok, reason = super().can_reduce(now)
        if not ok:
            return ok, reason
        power = self.power_kw()
        if power is not None and power * 1000 < float(
            self.config.get("min_power_w", 500)
        ):
            return False, "not_consuming"
        return True, "ok"
