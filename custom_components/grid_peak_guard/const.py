"""Constants for Grid Peak Guard."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "grid_peak_guard"
EVENT_ACTION: Final = f"{DOMAIN}_action"
STORAGE_VERSION: Final = 1

# Config entry data / options keys
CONF_GRID_POWER_ENTITY: Final = "grid_power_entity"
CONF_INVERT_GRID_POWER: Final = "invert_grid_power"
CONF_IMPORT_ENERGY_ENTITY: Final = "import_energy_entity"
CONF_TARGET_KW: Final = "target_kw"
CONF_MINIMUM_KW: Final = "minimum_kw"
CONF_HARD_MARGIN_KW: Final = "hard_margin_kw"
CONF_WINDOW_MINUTES: Final = "window_minutes"
CONF_ESCALATION_WAIT_S: Final = "escalation_wait_s"
CONF_SETTLE_S: Final = "settle_s"
CONF_UPDATE_INTERVAL_S: Final = "update_interval_s"
CONF_USE_MONTH_PEAK: Final = "use_month_peak"
CONF_SIMULATION: Final = "simulation"

# Tariff
CONF_ENERGY_PRICE: Final = "energy_price"
CONF_PRICE_ENTITY: Final = "price_entity"
CONF_GRID_ENERGY_PRICE: Final = "grid_energy_price"
CONF_POWER_PRICE: Final = "power_price"
CONF_POWER_THRESHOLD_KW: Final = "power_threshold_kw"
CONF_POWER_FACTOR_ABOVE: Final = "power_factor_above"

# Devices
CONF_DEVICES: Final = "devices"
CONF_DEVICE_ID: Final = "id"
CONF_CATEGORY: Final = "category"
CONF_PROFILE: Final = "profile"
CONF_NAME: Final = "name"
CONF_PRIORITY: Final = "priority"

# Defaults
DEFAULT_TARGET_KW: Final = 5.0
DEFAULT_MINIMUM_KW: Final = 2.0
DEFAULT_HARD_MARGIN_KW: Final = 2.0
DEFAULT_WINDOW_MINUTES: Final = 15
DEFAULT_ESCALATION_WAIT_S: Final = 60
DEFAULT_SETTLE_S: Final = 30
DEFAULT_UPDATE_INTERVAL_S: Final = 10
DEFAULT_POWER_THRESHOLD_KW: Final = 10.0
DEFAULT_POWER_FACTOR_ABOVE: Final = 2.0

WINDOW_MINUTE_CHOICES: Final = (5, 10, 15, 20, 30, 60)

# Energy integration: gaps longer than this are not bridged by the last sample.
MAX_INTEGRATION_GAP_S: Final = 60.0

# Outdoor temperature bands for heat pump learning (°C).
TEMP_BAND_COLD_BELOW: Final = 2.0
TEMP_BAND_WARM_FROM: Final = 12.0
BAND_COLD: Final = "cold"
BAND_MILD: Final = "mild"
BAND_WARM: Final = "warm"
BANDS: Final = (BAND_COLD, BAND_MILD, BAND_WARM)

# Minimum probability for "next expected start" of a heat pump.
FORECAST_MIN_PROBABILITY: Final = 0.3
