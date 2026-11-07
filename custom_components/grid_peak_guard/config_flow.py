"""Config and options flow for Grid Peak Guard."""

from __future__ import annotations

from typing import Any
import uuid

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
import voluptuous as vol

from .const import (
    CONF_CATEGORY,
    CONF_DEVICE_ID,
    CONF_DEVICES,
    CONF_ENERGY_PRICE,
    CONF_ESCALATION_WAIT_S,
    CONF_GRID_ENERGY_PRICE,
    CONF_GRID_POWER_ENTITY,
    CONF_HARD_MARGIN_KW,
    CONF_IMPORT_ENERGY_ENTITY,
    CONF_INVERT_GRID_POWER,
    CONF_MINIMUM_KW,
    CONF_NAME,
    CONF_POWER_FACTOR_ABOVE,
    CONF_POWER_PRICE,
    CONF_POWER_THRESHOLD_KW,
    CONF_PRICE_ENTITY,
    CONF_PRIORITY,
    CONF_PROFILE,
    CONF_SETTLE_S,
    CONF_SIMULATION,
    CONF_TARGET_KW,
    CONF_UPDATE_INTERVAL_S,
    CONF_USE_MONTH_PEAK,
    CONF_WINDOW_MINUTES,
    DEFAULT_ESCALATION_WAIT_S,
    DEFAULT_HARD_MARGIN_KW,
    DEFAULT_MINIMUM_KW,
    DEFAULT_POWER_FACTOR_ABOVE,
    DEFAULT_POWER_THRESHOLD_KW,
    DEFAULT_SETTLE_S,
    DEFAULT_TARGET_KW,
    DEFAULT_UPDATE_INTERVAL_S,
    DEFAULT_WINDOW_MINUTES,
    DOMAIN,
    WINDOW_MINUTE_CHOICES,
)
from .devices import CATEGORIES, DEVICE_REGISTRY, FieldSpec
from .devices.base import KIND_BOOL, KIND_ENTITY, KIND_NUMBER
from .profile_loader import GENERIC_PROFILE, async_get_profiles, suggest_entities

DEFAULT_TITLE = "Grid Peak Guard"


def _num(
    minimum: float, maximum: float, step: float, unit: str | None = None
) -> NumberSelector:
    config = NumberSelectorConfig(
        min=minimum, max=maximum, step=step, mode=NumberSelectorMode.BOX
    )
    if unit:
        config["unit_of_measurement"] = unit
    return NumberSelector(config)


def _opt(key: str, value: Any) -> vol.Optional:
    """Return an optional key that can be cleared (suggested instead of default)."""
    return vol.Optional(key, description={"suggested_value": value})


def _measurement_schema(values: dict[str, Any]) -> dict[Any, Any]:
    return {
        vol.Required(
            CONF_GRID_POWER_ENTITY,
            default=values.get(CONF_GRID_POWER_ENTITY, vol.UNDEFINED),
        ): EntitySelector(EntitySelectorConfig(domain="sensor", device_class="power")),
        vol.Required(
            CONF_INVERT_GRID_POWER, default=values.get(CONF_INVERT_GRID_POWER, False)
        ): BooleanSelector(),
        _opt(
            CONF_IMPORT_ENERGY_ENTITY, values.get(CONF_IMPORT_ENERGY_ENTITY)
        ): EntitySelector(EntitySelectorConfig(domain="sensor", device_class="energy")),
    }


def _settings_schema(values: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            **_measurement_schema(values),
            vol.Required(
                CONF_TARGET_KW, default=values.get(CONF_TARGET_KW, DEFAULT_TARGET_KW)
            ): _num(0.5, 100, 0.1, "kW"),
            vol.Required(
                CONF_MINIMUM_KW, default=values.get(CONF_MINIMUM_KW, DEFAULT_MINIMUM_KW)
            ): _num(0, 50, 0.1, "kW"),
            vol.Required(
                CONF_HARD_MARGIN_KW,
                default=values.get(CONF_HARD_MARGIN_KW, DEFAULT_HARD_MARGIN_KW),
            ): _num(0.1, 50, 0.1, "kW"),
            vol.Required(
                CONF_WINDOW_MINUTES,
                default=str(values.get(CONF_WINDOW_MINUTES, DEFAULT_WINDOW_MINUTES)),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[str(m) for m in WINDOW_MINUTE_CHOICES],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_ESCALATION_WAIT_S,
                default=values.get(CONF_ESCALATION_WAIT_S, DEFAULT_ESCALATION_WAIT_S),
            ): _num(10, 600, 5, "s"),
            vol.Required(
                CONF_SETTLE_S, default=values.get(CONF_SETTLE_S, DEFAULT_SETTLE_S)
            ): _num(0, 300, 5, "s"),
            vol.Required(
                CONF_UPDATE_INTERVAL_S,
                default=values.get(CONF_UPDATE_INTERVAL_S, DEFAULT_UPDATE_INTERVAL_S),
            ): _num(5, 60, 1, "s"),
            vol.Required(
                CONF_USE_MONTH_PEAK, default=values.get(CONF_USE_MONTH_PEAK, True)
            ): BooleanSelector(),
        }
    )


def _tariff_schema(values: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_ENERGY_PRICE, default=values.get(CONF_ENERGY_PRICE, 0.0)
            ): _num(0, 10, 0.0001),
            _opt(CONF_PRICE_ENTITY, values.get(CONF_PRICE_ENTITY)): EntitySelector(
                EntitySelectorConfig(domain=["sensor", "input_number"])
            ),
            vol.Required(
                CONF_GRID_ENERGY_PRICE, default=values.get(CONF_GRID_ENERGY_PRICE, 0.0)
            ): _num(0, 10, 0.0001),
            vol.Required(
                CONF_POWER_PRICE, default=values.get(CONF_POWER_PRICE, 0.0)
            ): _num(0, 1000, 0.01),
            vol.Required(
                CONF_POWER_THRESHOLD_KW,
                default=values.get(CONF_POWER_THRESHOLD_KW, DEFAULT_POWER_THRESHOLD_KW),
            ): _num(0, 1000, 0.1, "kW"),
            vol.Required(
                CONF_POWER_FACTOR_ABOVE,
                default=values.get(CONF_POWER_FACTOR_ABOVE, DEFAULT_POWER_FACTOR_ABOVE),
            ): _num(1, 10, 0.1),
        }
    )


def _field_selector(spec: FieldSpec) -> Any:
    if spec.kind == KIND_ENTITY:
        return EntitySelector(EntitySelectorConfig(domain=list(spec.domains)))
    if spec.kind == KIND_NUMBER:
        return _num(
            spec.minimum or 0, spec.maximum or 100000, spec.step or 1, spec.unit
        )
    if spec.kind == KIND_BOOL:
        return BooleanSelector()
    return TextSelector()


def device_schema(fields: tuple[FieldSpec, ...], values: dict[str, Any]) -> vol.Schema:
    """Build the form for a device category from its field specs."""
    schema: dict[Any, Any] = {}
    for spec in fields:
        value = values.get(spec.key, spec.default)
        if spec.required:
            key = vol.Required(
                spec.key, default=value if value is not None else vol.UNDEFINED
            )
        elif spec.kind in (KIND_NUMBER, KIND_BOOL) and value is not None:
            key = vol.Optional(spec.key, default=value)
        else:
            key = _opt(spec.key, value)
        schema[key] = _field_selector(spec)
    return vol.Schema(schema)


def validate_device(category: str, data: dict[str, Any]) -> dict[str, str]:
    """Return form errors for a device configuration."""
    errors: dict[str, str] = {}
    if (
        category == "heat_pump"
        and data.get("control_entity")
        and not data.get("reduce_value")
    ):
        errors["reduce_value"] = "reduce_value_required"
    return errors


class GridPeakGuardConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the grid measurement and the target."""
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_GRID_POWER_ENTITY])
            self._abort_if_unique_id_configured()
            title = user_input.pop(CONF_NAME, None) or DEFAULT_TITLE
            options = {
                CONF_TARGET_KW: user_input.pop(CONF_TARGET_KW),
                CONF_SIMULATION: user_input.pop(CONF_SIMULATION),
                CONF_DEVICES: [],
            }
            return self.async_create_entry(
                title=title, data=user_input, options=options
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_TITLE): TextSelector(),
                **_measurement_schema({}),
                vol.Required(CONF_TARGET_KW, default=DEFAULT_TARGET_KW): _num(
                    0.5, 100, 0.1, "kW"
                ),
                vol.Required(CONF_SIMULATION, default=True): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return GridPeakGuardOptionsFlow()


class GridPeakGuardOptionsFlow(OptionsFlow):
    """Settings, tariff and devices."""

    def __init__(self) -> None:
        """Initialize."""
        self._category: str | None = None
        self._profile_defaults: dict[str, Any] = {}
        self._editing: dict[str, Any] | None = None

    @property
    def _values(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    @property
    def _devices(self) -> list[dict[str, Any]]:
        return list(self.config_entry.options.get(CONF_DEVICES, []))

    def _save(self, **changes: Any) -> ConfigFlowResult:
        return self.async_create_entry(data={**self.config_entry.options, **changes})

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the main menu."""
        menu = ["settings", "tariff", "add_device"]
        if self._devices:
            menu += ["edit_device", "remove_device"]
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """General settings."""
        if user_input is not None:
            user_input[CONF_WINDOW_MINUTES] = int(user_input[CONF_WINDOW_MINUTES])
            user_input.setdefault(CONF_IMPORT_ENERGY_ENTITY, None)
            return self._save(**user_input)
        return self.async_show_form(
            step_id="settings", data_schema=_settings_schema(self._values)
        )

    async def async_step_tariff(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Tariff settings."""
        if user_input is not None:
            user_input.setdefault(CONF_PRICE_ENTITY, None)
            return self._save(**user_input)
        return self.async_show_form(
            step_id="tariff", data_schema=_tariff_schema(self._values)
        )

    # -- devices ----------------------------------------------------------------

    async def async_step_add_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a device category."""
        if user_input is not None:
            self._category = user_input[CONF_CATEGORY]
            self._editing = None
            return await self.async_step_profile()
        schema = vol.Schema(
            {
                vol.Required(CONF_CATEGORY): SelectSelector(
                    SelectSelectorConfig(
                        options=list(CATEGORIES),
                        translation_key="category",
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(step_id="add_device", data_schema=schema)

    async def async_step_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a device model profile."""
        assert self._category is not None
        profiles = (await async_get_profiles(self.hass)).get(self._category, {})
        if user_input is not None or len(profiles) <= 1:
            profile_id = (user_input or {}).get(CONF_PROFILE) or next(
                iter(profiles), GENERIC_PROFILE
            )
            cls = DEVICE_REGISTRY[self._category]
            defaults: dict[str, Any] = {
                CONF_PRIORITY: cls.default_priority,
                CONF_PROFILE: profile_id,
            }
            profile = profiles.get(profile_id)
            if profile is not None:
                defaults.update(profile.defaults)
                domains = {
                    f.key: f.domains for f in cls.fields if f.kind == KIND_ENTITY
                }
                defaults.update(suggest_entities(self.hass, profile, domains))
                defaults.setdefault(CONF_NAME, profile.name)
            self._profile_defaults = defaults
            return await self.async_step_device()
        options = [
            SelectOptionDict(value=p.id, label=p.name) for p in profiles.values()
        ]
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PROFILE, default=next(iter(profiles))
                ): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST)
                )
            }
        )
        return self.async_show_form(step_id="profile", data_schema=schema)

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the device fields."""
        assert self._category is not None
        cls = DEVICE_REGISTRY[self._category]
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = validate_device(self._category, user_input)
            if not errors:
                base = self._editing or {
                    CONF_DEVICE_ID: uuid.uuid4().hex,
                    CONF_CATEGORY: self._category,
                    CONF_PROFILE: self._profile_defaults.get(
                        CONF_PROFILE, GENERIC_PROFILE
                    ),
                }
                device = {
                    CONF_DEVICE_ID: base[CONF_DEVICE_ID],
                    CONF_CATEGORY: base[CONF_CATEGORY],
                    CONF_PROFILE: base.get(CONF_PROFILE, GENERIC_PROFILE),
                    **user_input,
                }
                device[CONF_PRIORITY] = int(device[CONF_PRIORITY])
                devices = [
                    d
                    for d in self._devices
                    if d[CONF_DEVICE_ID] != device[CONF_DEVICE_ID]
                ]
                devices.append(device)
                return self._save(**{CONF_DEVICES: devices})
        values = user_input or self._editing or self._profile_defaults
        return self.async_show_form(
            step_id="device",
            data_schema=device_schema(cls.fields, values),
            errors=errors,
            description_placeholders={"category": self._category},
        )

    def _device_choice_schema(self) -> vol.Schema:
        options = [
            SelectOptionDict(
                value=d[CONF_DEVICE_ID],
                label=f"{d.get(CONF_NAME)} ({d[CONF_CATEGORY]})",
            )
            for d in self._devices
        ]
        return vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST)
                )
            }
        )

    async def async_step_edit_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a device to edit."""
        if user_input is not None:
            self._editing = next(
                d
                for d in self._devices
                if d[CONF_DEVICE_ID] == user_input[CONF_DEVICE_ID]
            )
            self._category = self._editing[CONF_CATEGORY]
            return await self.async_step_device()
        return self.async_show_form(
            step_id="edit_device", data_schema=self._device_choice_schema()
        )

    async def async_step_remove_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove a device (it is restored by the reload)."""
        if user_input is not None:
            devices = [
                d
                for d in self._devices
                if d[CONF_DEVICE_ID] != user_input[CONF_DEVICE_ID]
            ]
            return self._save(**{CONF_DEVICES: devices})
        return self.async_show_form(
            step_id="remove_device", data_schema=self._device_choice_schema()
        )
