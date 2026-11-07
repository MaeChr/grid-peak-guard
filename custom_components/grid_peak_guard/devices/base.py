"""Base class, field specs and registry for controllable device categories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any, ClassVar

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfPower
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError

from ..const import CONF_DEVICE_ID, CONF_NAME, CONF_PRIORITY, EVENT_ACTION

_LOGGER = logging.getLogger(__name__)

# Field kinds used by the options flow to build selectors.
KIND_ENTITY = "entity"
KIND_NUMBER = "number"
KIND_BOOL = "bool"
KIND_TEXT = "text"

ON_OFF_DOMAINS = ("switch", "input_boolean", "light", "fan")
NUMBER_DOMAINS = ("number", "input_number")
SELECT_DOMAINS = ("select", "input_select")
CLIMATE_DOMAINS = ("climate",)


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """Describes one configuration field of a device category."""

    key: str
    kind: str
    required: bool = False
    default: Any = None
    domains: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    unit: str | None = None


# Fields every device has.
COMMON_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(CONF_NAME, KIND_TEXT, required=True),
    FieldSpec(CONF_PRIORITY, KIND_NUMBER, required=True, minimum=1, maximum=99, step=1),
)

POWER_FIELD = FieldSpec(
    "power_entity", KIND_ENTITY, domains=("sensor",)
)  # optional unless a category overrides it

DEVICE_REGISTRY: dict[str, type[BaseDevice]] = {}


def register(cls: type[BaseDevice]) -> type[BaseDevice]:
    """Class decorator that registers a device category."""
    DEVICE_REGISTRY[cls.category] = cls
    return cls


def create_device(hass: HomeAssistant, config: dict[str, Any]) -> BaseDevice:
    """Instantiate the device class registered for ``config['category']``."""
    return DEVICE_REGISTRY[config["category"]](hass, config)


def state_to_kw(state: State | None) -> float | None:
    """Convert a power sensor state (W or kW) to kW."""
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, ""):
        return None
    try:
        value = float(state.state)
    except ValueError:
        return None
    unit = state.attributes.get("unit_of_measurement")
    if unit == UnitOfPower.KILO_WATT:
        return value
    if unit == UnitOfPower.MEGA_WATT:
        return value * 1000.0
    return value / 1000.0  # W is the default


def state_to_float(state: State | None) -> float | None:
    """Numeric value of a state or ``None``."""
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, ""):
        return None
    try:
        return float(state.state)
    except ValueError:
        return None


def parse_on_off(value: Any) -> bool:
    """Interpret a configured value as on/off."""
    return str(value).strip().lower() in ("on", "true", "1", "yes", "an", "ein")


class BaseDevice:
    """A controllable (or monitored) load.

    Subclasses define ``category``, ``default_priority`` and ``fields`` and may
    override ``can_reduce``, ``should_release``, ``update`` and
    ``expected_extra_kw``.

    Safety contract:
    * ``async_reduce`` stores the previous value before changing anything.
    * ``async_restore`` always restores that value, in the same mode
      (simulated or real) the intervention was made in.
    * In simulation mode no service is called; only an event is fired.
    """

    category: ClassVar[str] = ""
    default_priority: ClassVar[int] = 50
    fields: ClassVar[tuple[FieldSpec, ...]] = ()
    controllable: ClassVar[bool] = True

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        """Initialize from the stored device configuration."""
        self.hass = hass
        self.config = config
        self.device_id: str = config[CONF_DEVICE_ID]
        self.name: str = config.get(CONF_NAME) or self.category
        self.priority: int = int(config.get(CONF_PRIORITY, self.default_priority))
        self.control_entity: str | None = config.get("control_entity")
        self.power_entity: str | None = config.get("power_entity")
        self.engaged_at: datetime | None = None
        self.engaged_simulated: bool = False
        self.previous_value: Any = None
        self.last_reason: str | None = None

    # -- information --------------------------------------------------------

    @property
    def engaged(self) -> bool:
        """Whether this device is currently reduced by us."""
        return self.engaged_at is not None

    def power_kw(self) -> float | None:
        """Return the current power of the device if a power sensor is configured."""
        if not self.power_entity:
            return None
        return state_to_kw(self.hass.states.get(self.power_entity))

    def can_reduce(self, now: datetime) -> tuple[bool, str]:
        """Whether the device may be reduced now, and why not."""
        if not self.controllable or not self.control_entity:
            return False, "not_controllable"
        state = self.hass.states.get(self.control_entity)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return False, "unavailable"
        return True, "ok"

    def should_release(self, now: datetime) -> bool:
        """Whether a protection limit requires releasing before window end."""
        return False

    def update(self, now: datetime) -> None:
        """Update learning and bookkeeping (called every cycle)."""

    def expected_extra_kw(self, now: datetime, window_end: datetime) -> float:
        """Return the expected extra load for the rest of the window (budget reserve)."""
        return 0.0

    def reduce_value(self) -> Any:
        """Value applied to ``control_entity`` while reduced."""
        return self.config.get("reduce_value")

    # -- control ------------------------------------------------------------

    async def async_reduce(self, now: datetime, simulation: bool) -> bool:
        """Reduce the load. Returns True if the device is now engaged."""
        if self.engaged:
            return True
        ok, reason = self.can_reduce(now)
        if not ok:
            self.last_reason = reason
            return False
        assert self.control_entity is not None
        self.previous_value = read_entity_value(self.hass, self.control_entity)
        if self.previous_value is None:
            self.last_reason = "unreadable"
            return False
        try:
            await apply_entity_value(
                self.hass, self.control_entity, self.reduce_value(), simulation
            )
        except (HomeAssistantError, ValueError) as err:
            # Keep the snapshot and stay engaged: the restore at window end
            # re-applies the previous value in case the call partly succeeded.
            _LOGGER.warning("Reducing %s failed: %s", self.name, err)
            self.engaged_at = now
            self.engaged_simulated = simulation
            self.last_reason = "reduce_failed"
            return False
        self.engaged_at = now
        self.engaged_simulated = simulation
        self.last_reason = "reduced"
        self._fire("reduce", self.reduce_value(), simulation)
        return True

    async def async_restore(self, now: datetime) -> bool:
        """Restore the previous value (in the mode the reduction was made in).

        Returns False if the restore failed; the device then stays engaged so
        the coordinator retries it.
        """
        if not self.engaged:
            return True
        assert self.control_entity is not None
        simulation = self.engaged_simulated
        try:
            await apply_entity_value(
                self.hass, self.control_entity, self.previous_value, simulation
            )
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.warning("Restoring %s failed, will retry: %s", self.name, err)
            self.last_reason = "restore_failed"
            return False
        self._fire("restore", self.previous_value, simulation)
        self.on_released(now)
        self.engaged_at = None
        self.previous_value = None
        self.last_reason = "restored"
        return True

    def on_released(self, now: datetime) -> None:
        """Run bookkeeping when a reduction ends."""

    # -- persistence ----------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """State that must survive a restart while engaged."""
        return {
            "engaged_at": self.engaged_at.isoformat() if self.engaged_at else None,
            "engaged_simulated": self.engaged_simulated,
            "previous_value": self.previous_value,
        }

    def load_snapshot(self, data: dict[str, Any]) -> None:
        """Restore state written by ``snapshot``."""
        raw = data.get("engaged_at")
        self.engaged_at = datetime.fromisoformat(raw) if raw else None
        self.engaged_simulated = bool(data.get("engaged_simulated", False))
        self.previous_value = data.get("previous_value")

    def learning_data(self) -> dict[str, Any] | None:
        """Return persistent learning data (if any)."""
        return None

    def load_learning_data(self, data: dict[str, Any] | None) -> None:
        """Restore learning data."""

    def diagnostics(self) -> dict[str, Any]:
        """Diagnostic information."""
        return {
            "category": self.category,
            "priority": self.priority,
            "engaged": self.engaged,
            "engaged_simulated": self.engaged_simulated,
            "last_reason": self.last_reason,
        }

    def _fire(self, action: str, value: Any, simulation: bool) -> None:
        self.hass.bus.async_fire(
            EVENT_ACTION,
            {
                "device_id": self.device_id,
                "name": self.name,
                "category": self.category,
                "action": action,
                "entity_id": self.control_entity,
                "value": value,
                "simulation": simulation,
            },
        )
        _LOGGER.info(
            "%s %s %s -> %s%s",
            action,
            self.name,
            self.control_entity,
            value,
            " (simulation)" if simulation else "",
        )


def read_entity_value(hass: HomeAssistant, entity_id: str) -> Any:
    """Read the current controllable value of an entity."""
    state = hass.states.get(entity_id)
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    domain = entity_id.split(".", 1)[0]
    if domain in ON_OFF_DOMAINS:
        return "on" if state.state == "on" else "off"
    if domain in NUMBER_DOMAINS:
        return state_to_float(state)
    if domain in CLIMATE_DOMAINS:
        return state.attributes.get("temperature")
    return state.state


async def apply_entity_value(
    hass: HomeAssistant, entity_id: str, value: Any, simulation: bool
) -> None:
    """Apply ``value`` to an entity via a service call (skipped in simulation)."""
    if simulation or value is None:
        return
    domain = entity_id.split(".", 1)[0]
    service: str
    data: dict[str, Any] = {"entity_id": entity_id}
    if domain in ON_OFF_DOMAINS:
        service = "turn_on" if parse_on_off(value) else "turn_off"
    elif domain in NUMBER_DOMAINS:
        service = "set_value"
        data["value"] = float(value)
    elif domain in SELECT_DOMAINS:
        service = "select_option"
        data["option"] = str(value)
    elif domain in CLIMATE_DOMAINS:
        service = "set_temperature"
        data["temperature"] = float(value)
    else:
        _LOGGER.warning("Unsupported domain for control: %s", entity_id)
        return
    await hass.services.async_call(domain, service, data, blocking=True)
