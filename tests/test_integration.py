"""End-to-end tests against Home Assistant."""

from datetime import UTC, datetime, timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_mock_service,
)

from custom_components.grid_peak_guard.const import DOMAIN, EVENT_ACTION
from custom_components.grid_peak_guard.diagnostics import (
    async_get_config_entry_diagnostics,
)

START = datetime(2026, 11, 2, 10, 0, 0, tzinfo=UTC)
GRID = "sensor.grid_power"

BATTERY = {
    "id": "bat1",
    "category": "battery",
    "name": "Battery",
    "priority": 10,
    "control_entity": "number.battery_max_grid_charge",
    "reduce_value": "0",
}
WALLBOX = {
    "id": "wb1",
    "category": "wallbox",
    "name": "Wallbox",
    "priority": 20,
    "control_entity": "number.wallbox_current",
    "reduce_value": "6",
    "min_power_w": 0,
}
HEAT_PUMP = {
    "id": "hp1",
    "category": "heat_pump",
    "name": "Heat pump",
    "priority": 35,
    "control_entity": "switch.heat_pump_lock",
    "reduce_value": "on",
    "power_entity": "sensor.heat_pump_power",
    "run_threshold_w": 300,
    "min_runtime_min": 10,
    "max_block_min": 5,
    "max_block_day_min": 120,
    "min_pause_min": 30,
}
APPLIANCE = {
    "id": "ap1",
    "category": "appliance",
    "name": "Dishwasher",
    "priority": 30,
    "control_entity": "switch.dishwasher_plug",
    "power_entity": "sensor.dishwasher_power",
    "standby_w": 5,
    "idle_min": 10,
    "max_delay_min": 60,
}


def _set_states(hass: HomeAssistant, grid_w: float = 1000) -> None:
    hass.states.async_set(GRID, str(grid_w), {"unit_of_measurement": "W"})
    hass.states.async_set("number.battery_max_grid_charge", "3000")
    hass.states.async_set("number.wallbox_current", "16")
    hass.states.async_set("switch.heat_pump_lock", "off")
    hass.states.async_set("sensor.heat_pump_power", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("switch.dishwasher_plug", "on")
    hass.states.async_set("sensor.dishwasher_power", "1", {"unit_of_measurement": "W"})


async def _setup(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    devices: list[dict[str, Any]],
    simulation: bool = False,
    **options: Any,
) -> MockConfigEntry:
    freezer.move_to(START)
    _set_states(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Grid Peak Guard",
        data={"grid_power_entity": GRID},
        options={
            "target_kw": 5.0,
            "simulation": simulation,
            "settle_s": 0,
            "escalation_wait_s": 60,
            "hard_margin_kw": 20.0,
            "devices": devices,
            **options,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _tick(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    seconds: float,
    grid_w: float | None = None,
) -> None:
    freezer.tick(timedelta(seconds=seconds))
    if grid_w is not None:
        hass.states.async_set(GRID, str(grid_w), {"unit_of_measurement": "W"})
    coordinator = entry.runtime_data
    coordinator.async_set_updated_data(await coordinator.async_cycle(dt_util.utcnow()))
    await hass.async_block_till_done()


async def _run_until(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    target: datetime,
    grid_w: float | None = None,
) -> None:
    """Run regular 10 s cycles until ``target`` (no measurement gaps)."""
    if grid_w is not None:
        hass.states.async_set(GRID, str(grid_w), {"unit_of_measurement": "W"})
    while dt_util.utcnow() < target:
        step = min(10.0, (target - dt_util.utcnow()).total_seconds())
        await _tick(hass, entry, freezer, step)


async def test_staged_escalation_and_restore_at_window_end(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    number_calls = async_mock_service(hass, "number", "set_value")
    entry = await _setup(hass, freezer, [WALLBOX, BATTERY])

    await _tick(hass, entry, freezer, 10, grid_w=8000)
    # First stage (battery, priority 10) immediately
    assert [c.data for c in number_calls] == [
        {"entity_id": "number.battery_max_grid_charge", "value": 0.0}
    ]
    await _tick(hass, entry, freezer, 30)
    assert len(number_calls) == 1  # waiting time not over
    await _tick(hass, entry, freezer, 40)
    assert number_calls[-1].data == {
        "entity_id": "number.wallbox_current",
        "value": 6.0,
    }
    assert entry.runtime_data.data.level == 2
    assert (
        hass.states.get("binary_sensor.grid_peak_guard_intervention_active").state
        == "on"
    )

    # Run regularly until the next window: everything restored
    await _run_until(hass, entry, freezer, START + timedelta(minutes=14, seconds=55))
    await _tick(hass, entry, freezer, 10, grid_w=1000)
    assert dt_util.utcnow() >= START + timedelta(minutes=15)
    restored = {c.data["entity_id"]: c.data["value"] for c in number_calls[2:]}
    assert restored == {
        "number.battery_max_grid_charge": 3000.0,
        "number.wallbox_current": 16.0,
    }
    assert entry.runtime_data.data.level == 0
    # Month peak recorded from the finished window
    assert entry.runtime_data.data.month_peak_kw > 5.0


async def test_hard_limit_engages_all_at_once(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    number_calls = async_mock_service(hass, "number", "set_value")
    entry = await _setup(hass, freezer, [BATTERY, WALLBOX], hard_margin_kw=1.0)
    await _tick(hass, entry, freezer, 10, grid_w=9000)
    assert len(number_calls) == 2
    assert entry.runtime_data.data.reason == "hard_limit"


async def test_simulation_calls_no_services(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    number_calls = async_mock_service(hass, "number", "set_value")
    events = async_capture_events(hass, EVENT_ACTION)
    entry = await _setup(hass, freezer, [BATTERY], simulation=True)
    await _tick(hass, entry, freezer, 10, grid_w=8000)
    assert number_calls == []
    assert events[-1].data["action"] == "reduce"
    assert events[-1].data["simulation"] is True

    # Switching simulation off restores the simulated intervention first
    # (without a service call), then control continues for real.
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.grid_peak_guard_simulation_mode"},
        blocking=True,
    )
    actions = [(e.data["action"], e.data["simulation"]) for e in events]
    assert actions == [("reduce", True), ("restore", True), ("reduce", False)]
    assert [c.data["value"] for c in number_calls] == [0.0]


async def test_disable_control_restores(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    number_calls = async_mock_service(hass, "number", "set_value")
    entry = await _setup(hass, freezer, [BATTERY])
    await _tick(hass, entry, freezer, 10, grid_w=8000)
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.grid_peak_guard_control"},
        blocking=True,
    )
    assert number_calls[-1].data["value"] == 3000.0
    await _tick(hass, entry, freezer, 70, grid_w=8000)
    assert number_calls[-1].data["value"] == 3000.0  # nothing re-engaged


async def test_heat_pump_protection_times(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await _setup(hass, freezer, [HEAT_PUMP])
    # Mock after setup: loading the switch platform registers the real services.
    switch_on = async_mock_service(hass, "switch", "turn_on")
    switch_off = async_mock_service(hass, "switch", "turn_off")

    # Compressor just started: minimum runtime protects it
    hass.states.async_set(
        "sensor.heat_pump_power", "2500", {"unit_of_measurement": "W"}
    )
    await _tick(hass, entry, freezer, 10, grid_w=8000)
    assert switch_on == []
    hp = entry.runtime_data.devices[0]
    assert hp.last_reason == "min_runtime"

    # After the minimum runtime the lock is set (next stage after waiting time)
    await _run_until(hass, entry, freezer, START + timedelta(minutes=10, seconds=20))
    assert hp.last_reason == "reduced"
    assert len(switch_on) == 1
    # Maximum lock duration (5 min) releases before window end
    await _tick(hass, entry, freezer, 5 * 60 + 1)
    assert len(switch_off) == 1
    assert not hp.engaged
    # Minimum pause prevents re-locking in the next window
    await _run_until(hass, entry, freezer, START + timedelta(minutes=30, seconds=10))
    assert len(switch_on) == 1
    assert hp.last_reason == "min_pause"


async def test_appliance_never_interrupted(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await _setup(hass, freezer, [APPLIANCE])
    switch_off = async_mock_service(hass, "switch", "turn_off")
    async_mock_service(hass, "switch", "turn_on")
    hass.states.async_set(
        "sensor.dishwasher_power", "1800", {"unit_of_measurement": "W"}
    )
    await _tick(hass, entry, freezer, 10, grid_w=8000)
    assert switch_off == []
    assert entry.runtime_data.devices[0].last_reason == "running"

    # Idle, but not long enough
    hass.states.async_set("sensor.dishwasher_power", "1", {"unit_of_measurement": "W"})
    await _run_until(hass, entry, freezer, START + timedelta(minutes=9))
    assert switch_off == []
    assert entry.runtime_data.devices[0].last_reason == "not_idle_long_enough"
    # Idle for 10 minutes -> start is delayed
    await _run_until(hass, entry, freezer, START + timedelta(minutes=10, seconds=30))
    assert len(switch_off) == 1


async def test_restart_restores_persisted_intervention(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    number_calls = async_mock_service(hass, "number", "set_value")
    entry = await _setup(hass, freezer, [BATTERY])
    await _tick(hass, entry, freezer, 10, grid_w=8000)
    assert entry.runtime_data.devices[0].engaged

    # Simulate a crash: drop the entry without unloading, then set up again.
    coordinator = entry.runtime_data
    await coordinator.async_save_now()
    saved = coordinator._store_data()
    assert saved["devices"]["bat1"]["previous_value"] == 3000.0

    from custom_components.grid_peak_guard.coordinator import (
        GridPeakGuardCoordinator,
    )

    fresh = GridPeakGuardCoordinator(hass, entry)
    await fresh.async_load()
    assert number_calls[-1].data == {
        "entity_id": "number.battery_max_grid_charge",
        "value": 3000.0,
    }
    assert not fresh.devices[0].engaged


async def test_unload_restores(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    number_calls = async_mock_service(hass, "number", "set_value")
    entry = await _setup(hass, freezer, [BATTERY])
    await _tick(hass, entry, freezer, 10, grid_w=8000)
    coordinator = entry.runtime_data
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert number_calls[-1].data["value"] == 3000.0
    # A late cycle after the final restore must not engage again
    await coordinator.async_cycle(dt_util.utcnow())
    assert number_calls[-1].data["value"] == 3000.0


async def test_failed_restore_is_retried(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await _setup(hass, freezer, [BATTERY])
    calls: list = []
    fail = {"on": False}

    async def handler(call):
        if fail["on"]:
            from homeassistant.exceptions import HomeAssistantError

            raise HomeAssistantError("device offline")
        calls.append(call.data["value"])

    hass.services.async_register("number", "set_value", handler)
    await _tick(hass, entry, freezer, 10, grid_w=8000)
    fail["on"] = True
    await _run_until(
        hass, entry, freezer, START + timedelta(minutes=15, seconds=5), 1000
    )
    assert entry.runtime_data.devices[0].engaged  # still waiting for restore
    fail["on"] = False
    await _tick(hass, entry, freezer, 10)
    assert calls == [0.0, 3000.0]
    assert not entry.runtime_data.devices[0].engaged


async def test_sensors_and_diagnostics(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    async_mock_service(hass, "number", "set_value")
    entry = await _setup(hass, freezer, [BATTERY, HEAT_PUMP], power_price=4.0)
    await _tick(hass, entry, freezer, 60, grid_w=4000)
    state = hass.states.get("sensor.grid_peak_guard_projected_window_average")
    assert state is not None
    assert float(state.state) > 0
    assert hass.states.get("sensor.grid_peak_guard_effective_limit").state == "5.0"
    assert hass.states.get("sensor.grid_peak_guard_heat_pump_start_probability")
    assert (
        float(hass.states.get("sensor.grid_peak_guard_monthly_power_charge").state)
        == 8.0
    )

    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["entry"]["data"]["grid_power_entity"] == "**REDACTED**"
    assert diag["entry"]["options"]["devices"][0]["control_entity"] == "**REDACTED**"
    assert len(diag["devices"]) == 2
