"""Holds all the local enumerations used in the project."""

from dataclasses import dataclass
from enum import StrEnum

SCHEMA_VERSION = 1  # Version of the system_state schema we expect
CONFIG_FILE = "config.yaml"
PRICES_DATA_FILE = "latest_prices.json"
PRICE_SLOT_INTERVAL = 5   # Length in minutes for each price slot
WEEKDAY_ABBREVIATIONS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DEFAULT_PRICE = 30.0
PRICES_DATA_FILE = "latest_prices.json"
PRICE_SLOT_INTERVAL = 5   # Length in minutes for each price slot
RUNPLAN_CHECK_INTERVAL = 30  # Minutes between checking if we need to regenerate run plan
FAILED_RUNPLAN_CHECK_INTERVAL = 10  # Minutes between checking if we need to regenerate run plan when then previous one failed or was incomplete


class AmberAPIMode(StrEnum):
    """Mode for Amber API."""
    LIVE = "Live"
    OFFLINE = "Offline"
    DISABLED = "Disabled"


class AmberChannel(StrEnum):
    """Mode for Amber channel."""
    GENERAL = "general"
    CONTROLLED_LOAD = "controlledLoad"


class PriceFetchMode(StrEnum):
    """Mode for fetching prices."""
    NORMAL = "normal"
    SORTED = "sorted"


class InputMode(StrEnum):
    """Input mode for devices."""
    IGNORE = "Ignore"
    TURN_ON = "TurnOn"
    TURN_OFF = "TurnOff"


@dataclass
class OutputStatusData:
    """Used to pass status data into RunHistory."""
    meter_reading: float
    target_hours: float | None
    current_price: float


@dataclass
class Command:
    """Define the structure for commands to be posted to Controller."""
    kind: str
    payload: dict[str, str]


class LookupMode(StrEnum):
    """Lookup mode used for PowerController._find_output()."""
    ID = "id"
    NAME = "name"
    OUTPUT = "output"
    METER = "meter"
    INPUT = "input"
