"""Load with an adjustable setpoint or power level."""

from __future__ import annotations

from .base import (
    COMMON_FIELDS,
    KIND_ENTITY,
    KIND_TEXT,
    NUMBER_DOMAINS,
    ON_OFF_DOMAINS,
    POWER_FIELD,
    SELECT_DOMAINS,
    BaseDevice,
    FieldSpec,
    register,
)

CONTROL_DOMAINS_ALL = (*NUMBER_DOMAINS, *SELECT_DOMAINS, *ON_OFF_DOMAINS, "climate")


@register
class ModulatingDevice(BaseDevice):
    """Load with an adjustable setpoint (e.g. heating rod power, boiler setpoint)."""

    category = "modulating"
    default_priority = 25
    fields = (
        *COMMON_FIELDS,
        FieldSpec(
            "control_entity", KIND_ENTITY, required=True, domains=CONTROL_DOMAINS_ALL
        ),
        FieldSpec("reduce_value", KIND_TEXT, required=True),
        POWER_FIELD,
    )
