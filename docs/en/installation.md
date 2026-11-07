# Installation and setup

## Requirements

- Home Assistant 2025.8 or newer
- A sensor for the grid power (W or kW). Positive = import, negative = export; the sign can be inverted in the setup.
- Optional: a grid import energy meter (kWh). If set, the window energy is taken from it instead of integrating the power.

## Install via HACS

1. HACS → three-dot menu → **Custom repositories** → add `https://github.com/MaeChr/grid-peak-guard`, category **Integration**.
2. Install **Grid Peak Guard** and restart Home Assistant.

Manual: copy `custom_components/grid_peak_guard` into your `config/custom_components/` folder and restart.

## Setup

1. **Settings → Devices & services → Add integration → Grid Peak Guard.**
2. Choose the grid power sensor, the target average power and keep **Start in simulation mode** on.
3. Open **Configure** to add devices, tariff and general settings.

### General settings

| Option | Meaning |
|---|---|
| Target average power | Average import per window you want to stay below |
| Billed minimum power | Minimum power billed per month (e.g. 2 kW) |
| Hard limit margin | At limit + margin all stages engage at once |
| Measuring window | 15 minutes for most grid operators |
| Waiting time | Time between two escalation stages |
| Settling time | No escalation in the first seconds of a window (projection is noisy) |
| Raise limit to month peak | Do not reduce below a peak already billed this month |

### Devices

Choose a category, then a model profile. The profile fills in defaults and suggests matching entities — always check the suggestion. **Value while reduced** is applied to the control entity during an intervention (`on`/`off` for switches, a number, an option text or a temperature); the previous value is restored at window end.

Appliances (dishwasher, washing machine …) are only switched off when they have been idle for the configured time, so a running program is never interrupted. Only use this with appliances that keep or resume a delayed start after power returns, or use a vendor "start allowed" entity.

## Entities

- Sensors: projected window average, window average so far, effective limit, required reduction, month peak, last window average, window energy, escalation level, monthly power charge, monthly cost estimate; per heat pump: next expected start and start probability.
- Binary sensors: limit at risk, intervention active.
- Switches: control (off = restore everything and stop), simulation mode.

Every action fires the event `grid_peak_guard_action` with `device_id`, `name`, `category`, `action` (`reduce`/`restore`), `entity_id`, `value` and `simulation`.

## Going live

1. Run in simulation mode for a few days and compare the events with what you expect.
2. Switch simulation off. Interventions made in simulation are restored first (without service calls).
3. Check the diagnostics download (device page → Download diagnostics) when something looks wrong; entity IDs are redacted.
