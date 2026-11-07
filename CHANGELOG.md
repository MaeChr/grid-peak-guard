# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/), versioning: [SemVer](https://semver.org/).

## [0.2.0] - 2026-11-07

Rebuild of the integration in the public repository.

### Added
- Projection of the window average, effective limit (target, billed minimum, month peak) and required reduction.
- Escalation by priority with waiting time, hard limit engaging all stages, restore at window end from a persisted snapshot (also after restart, on unload and when control is switched off); failed restores are retried.
- Device modules with registry: battery, wallbox, modulating, switchable, heat pump, appliance (delay start only), monitor.
- JSON device profiles with defaults and regex entity suggestions.
- Heat pump: optional lock (utility contact, SG-Ready, setpoint) with minimum runtime, maximum lock duration, maximum lock time per day and minimum pause; start learning per hour and outdoor temperature band, next expected start, start probability, typical power/runtime, external start time with precedence, optional budget reserve.
- Tariff: fixed price or price entity, grid energy charge, power charge per kW and month, billed minimum power, factor above a threshold.
- Simulation mode (default on), `grid_peak_guard_action` events, diagnostics with redacted entity IDs.
- UI in German and English; documentation in German and English.
