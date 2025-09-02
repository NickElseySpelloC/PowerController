"""Holds all the enumerations used in the project. Saved here to avoid circular imports."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

CONFIG_FILE = "config.yaml"
PRICES_DATA_FILE = "latest_prices.json"
PRICE_SLOT_INTERVAL = 5   # Length in minutes for each price slot
WEEKDAY_ABBREVIATIONS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DEFAULT_PRICE = 25.0
PRICES_DATA_FILE = "latest_prices.json"
PRICE_SLOT_INTERVAL = 5   # Length in minutes for each price slot


# Override modes for the mobile app
class AppMode(StrEnum):
    ON = "on"
    OFF = "off"
    AUTO = "auto"


# To be replaced by the Output state snapshot
@dataclass
class LightState:
    light_id: str
    mode: AppMode = AppMode.AUTO
    is_on: bool = False
    name: str = ""


# Define the structure for commands to be posted to Controller
@dataclass
class Command:
    kind: str
    payload: dict[str, Any]


# Mode for Amber API
class AmberAPIMode(StrEnum):
    LIVE = "Live"
    OFFLINE = "Offline"
    DISABLED = "Disabled"


# Mode for creating run plans
class RunPlanMode(StrEnum):
    BEST_PRICE = "BestPrice"
    SCHEDULE = "Schedule"


# Enumerate the overall system state
class SystemState(StrEnum):
    DATE_OFF = "DateOff condition met for today"
    SCHEDULED = "Automatic control based on predefined schedule"
    BEST_PRICE = "Automatic control based on best price"


# Enumerate the reasons why the Output is off
class StateReasonOff(StrEnum):
    RUN_PLAN_COMPLETE = "No more run time required today"
    APP_MODE_OFF = "App has overridden the mode to off"
    INPUT_SWITCH_OFF = "Device input has overridden the mode to off"


# Enumerate the reasons why the Output is on
class StateReasonOn(StrEnum):
    APP_MODE_ON = "App has overridden the mode to on"
    INPUT_SWITCH_ON = "Device input has overridden the mode to on"
    SCHEDULED = "Scheduled run time"
    BEST_PRICE = "Best price run time"
