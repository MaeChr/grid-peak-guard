"""Config and options flow tests."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.grid_peak_guard.const import DOMAIN


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "sensor.grid", "500", {"unit_of_measurement": "W", "device_class": "power"}
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Peak",
            "grid_power_entity": "sensor.grid",
            "invert_grid_power": False,
            "target_kw": 4.0,
            "simulation": True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Peak"
    assert result["data"] == {
        "grid_power_entity": "sensor.grid",
        "invert_grid_power": False,
    }
    assert result["options"] == {"target_kw": 4.0, "simulation": True, "devices": []}

    # Same sensor cannot be configured twice
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Peak 2",
            "grid_power_entity": "sensor.grid",
            "invert_grid_power": False,
            "target_kw": 4.0,
            "simulation": True,
        },
    )
    assert result["type"] is FlowResultType.ABORT


async def _entry(hass: HomeAssistant):
    hass.states.async_set("sensor.grid", "500", {"unit_of_measurement": "W"})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Peak",
            "grid_power_entity": "sensor.grid",
            "invert_grid_power": False,
            "target_kw": 4.0,
            "simulation": True,
        },
    )
    await hass.async_block_till_done()
    return result["result"]


async def test_options_add_edit_remove_device(hass: HomeAssistant) -> None:
    entry = await _entry(hass)
    hass.states.async_set("sensor.heat_pump_power", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("switch.heat_pump_evu_lock", "off")

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert "edit_device" not in result["menu_options"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_device"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"category": "heat_pump"}
    )
    assert result["step_id"] == "profile"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"profile": "evu_lock"}
    )
    assert result["step_id"] == "device"
    # Profile defaults and regex suggestions are pre-filled
    schema_keys = {str(k): k for k in result["data_schema"].schema}
    assert (
        schema_keys["control_entity"].description["suggested_value"]
        == "switch.heat_pump_evu_lock"
    )

    # Missing reduce value with a control entity is rejected
    base = {
        "name": "HP",
        "priority": 35,
        "control_entity": "switch.heat_pump_evu_lock",
        "power_entity": "sensor.heat_pump_power",
        "run_threshold_w": 300,
        "min_runtime_min": 10,
        "max_block_min": 30,
        "max_block_day_min": 120,
        "min_pause_min": 30,
        "budget_reserve": False,
    }
    result = await hass.config_entries.options.async_configure(result["flow_id"], base)
    assert result["errors"] == {"reduce_value": "reduce_value_required"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**base, "reduce_value": "on"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    devices = entry.options["devices"]
    assert len(devices) == 1
    assert devices[0]["category"] == "heat_pump"
    assert devices[0]["profile"] == "evu_lock"
    device_id = devices[0]["id"]

    # Edit
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "edit_device"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"id": device_id}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**base, "reduce_value": "on", "priority": 40}
    )
    await hass.async_block_till_done()
    assert entry.options["devices"][0]["priority"] == 40
    assert entry.options["devices"][0]["id"] == device_id

    # Remove
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "remove_device"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"id": device_id}
    )
    await hass.async_block_till_done()
    assert entry.options["devices"] == []


async def test_options_settings(hass: HomeAssistant) -> None:
    entry = await _entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "settings"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "grid_power_entity": "sensor.grid",
            "invert_grid_power": True,
            "target_kw": 6.0,
            "minimum_kw": 2.0,
            "hard_margin_kw": 2.0,
            "window_minutes": "15",
            "escalation_wait_s": 60,
            "settle_s": 30,
            "update_interval_s": 10,
            "use_month_peak": True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["window_minutes"] == 15
    assert entry.options["target_kw"] == 6.0
    assert entry.options["invert_grid_power"] is True
