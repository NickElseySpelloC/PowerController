"""Holds all the local enumerations used in the project."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from org_enums import (
    StateReasonOff,
    StateReasonOn,
    SystemState,
)

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
USAGE_AGGREGATION_INTERVAL = 60  # Minutes between aggregating usage data


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
    power_draw: float
    is_on: bool
    target_hours: float | None
    current_price: float


@dataclass
class Command:
    """Define the structure for commands to be posted to Controller."""
    kind: str
    payload: dict[str, Any]


class OutputActionType(StrEnum):
    """Type of action to be taken for an output."""
    TURN_ON = "Turn On"
    TURN_OFF = "Turn Off"
    UPDATE_ON_STATE = "Update state while on"
    UPDATE_OFF_STATE = "Update state while off"


@dataclass
class OutputAction:
    """Define the structure for output actions."""
    worker_request_id: str | None
    type: OutputActionType
    system_state: SystemState
    reason: StateReasonOn | StateReasonOff


class LookupMode(StrEnum):
    """Lookup mode used for PowerController._find_output()."""
    ID = "id"
    NAME = "name"
    OUTPUT = "output"
    METER = "meter"
    INPUT = "input"
