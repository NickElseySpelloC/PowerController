"""Holds all the local enumerations used in the project."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

CONFIG_FILE = "config.yaml"
PRICES_DATA_FILE = "latest_prices.json"
PRICE_SLOT_INTERVAL = 5   # Length in minutes for each price slot
WEEKDAY_ABBREVIATIONS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DEFAULT_PRICE = 30.0
PRICES_DATA_FILE = "latest_prices.json"
PRICE_SLOT_INTERVAL = 5   # Length in minutes for each price slot


# Mode for Amber API
class AmberAPIMode(StrEnum):
    LIVE = "Live"
    OFFLINE = "Offline"
    DISABLED = "Disabled"


# Mode for Amber channel
class AmberChannel(StrEnum):
    GENERAL = "general"
    CONTROLLED_LOAD = "controlledLoad"


# Get prices mode
class PriceFetchMode(StrEnum):
    NORMAL = "normal"
    SORTED = "sorted"


class InputMode(StrEnum):
    IGNORE = "Ignore"
    TURN_ON = "TurnOn"
    TURN_OFF = "TurnOff"


# Used to pass status data into RunHistory
@dataclass
class OutputStatusData:
    meter_reading: float
    target_hours: float | None
    current_price: float


# Define the structure for commands to be posted to Controller
@dataclass
class Command:
    kind: str
    payload: dict[str, Any]


# Lookup mode used for PowerController._find_output()
class LookupMode(StrEnum):
    ID = "id"
    NAME = "name"
    OUTPUT = "output"
    METER = "meter"
    INPUT = "input"
