# Grid Peak Guard

[![Validate](https://github.com/MaeChr/grid-peak-guard/actions/workflows/validate.yml/badge.svg)](https://github.com/MaeChr/grid-peak-guard/actions/workflows/validate.yml)
[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)

*Deutsch: [README.de.md](README.de.md)*

Home Assistant custom integration that keeps the **averaged grid import per measuring window** (default 15 minutes) below a target. Built for power-based grid tariffs (e.g. Austria from 2027), usable in any country and with any device that Home Assistant can control.

## How it works

- **Projection** every few seconds: window energy so far + (current import + expected extra load) × remaining time.
- **Effective limit** = max(target, billed minimum power, month peak so far) — reducing below a peak that is already billed saves nothing.
- **Escalation** by priority, one stage per waiting time: battery (10) → wallbox (20) → modulating load (25) → switchable load / appliance (30) → heat pump (35). At the **hard limit** (limit + margin) all stages engage at once.
- **Window end:** every intervention is restored from a persisted snapshot — also after a restart, on unload and when control is switched off.
- **Simulation mode** (default on): decisions are only logged and fired as `grid_peak_guard_action` events; no device is touched.

## Device categories

| Category | Action | Protection |
|---|---|---|
| Battery | set a number/select/switch (e.g. stop grid charging) | minimum state of charge |
| Wallbox | reduce charging current or pause | only while charging |
| Modulating | set a lower setpoint/power level | – |
| Switchable | switch off | only while consuming, maximum off time |
| Heat pump | utility lock contact, SG-Ready or setpoint — optional | minimum runtime, max lock duration, max lock time per day, minimum pause |
| Appliance | **delay start only**, never interrupt | only after being idle for a while, maximum delay |
| Monitor | none | – |

Heat pumps learn their start times per hour and outdoor temperature band (cold < 2 °C ≤ mild < 12 °C ≤ warm), provide the next expected start and start probability, and can reserve budget for an expected start. An external start time entity takes precedence.

Concrete device models are JSON profiles in `custom_components/grid_peak_guard/profiles/<category>/` with defaults and entity suggestions — new models need no code.

## Installation

See [docs/en/installation.md](docs/en/installation.md). Requires Home Assistant 2025.8 or newer.

## Safety

Controlling batteries, chargers, heat pumps and appliances can have side effects. Start in simulation mode, check the events and sensors for a few days, and only then switch simulation off.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). License: [MIT](LICENSE).
