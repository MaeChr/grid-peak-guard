"""Home battery: stop grid charging or force discharge."""

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
    state_to_float,
)


@register
class BatteryDevice(BaseDevice):
    """Home battery: e.g. stop grid charging or force discharge."""

    category = "battery"
    default_priority = 10
    fields = (
        *COMMON_FIELDS,
        FieldSpec(
            "control_entity",
            KIND_ENTITY,
            required=True,
            domains=(*NUMBER_DOMAINS, *SELECT_DOMAINS, *ON_OFF_DOMAINS),
        ),
        FieldSpec("reduce_value", KIND_TEXT, required=True),
        FieldSpec("soc_entity", KIND_ENTITY, domains=("sensor", *NUMBER_DOMAINS)),
        FieldSpec(
            "min_soc", KIND_NUMBER, default=10, minimum=0, maximum=100, step=1, unit="%"
        ),
        POWER_FIELD,
    )

    def can_reduce(self, now: datetime) -> tuple[bool, str]:
        """Do not engage below the minimum state of charge."""
        ok, reason = super().can_reduce(now)
        if not ok:
            return ok, reason
        soc_entity = self.config.get("soc_entity")
        if soc_entity:
            soc = state_to_float(self.hass.states.get(soc_entity))
            if soc is not None and soc < float(self.config.get("min_soc", 10)):
                return False, "soc_below_minimum"
        return True, "ok"
