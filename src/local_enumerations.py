"""Holds all the local enumerations used in the project."""

import datetime as dt
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from org_enums import (
    StateReasonOff,
    StateReasonOn,
    SystemState,
)

SCHEMA_VERSION = 1  # Version of the system_state schema we expect
CONFIG_FILE = "config.yaml"
PRICE_SLOT_INTERVAL = 5   # Length in minutes for each price slot
WEEKDAY_ABBREVIATIONS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DEFAULT_PRICE = 30.0
PRICES_DATA_FILE = "latest_prices.json"
PRICE_SLOT_INTERVAL = 5   # Length in minutes for each price slot
RUNPLAN_CHECK_INTERVAL = 30  # Minutes between checking if we need to regenerate run plan
FAILED_RUNPLAN_CHECK_INTERVAL = 10  # Minutes between checking if we need to regenerate run plan when then previous one failed or was incomplete
USAGE_AGGREGATION_INTERVAL = 60  # Minutes between aggregating usage data
DUMP_SHELLY_SNAPSHOT = False  # Save the JSON snapshot to a file for debugging


# Amber API enumerations ======================================================
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


# Web interface command queue =================================================
@dataclass
class Command:
    """Define the structure for commands to be posted to Controller."""
    kind: str
    payload: dict[str, Any]


# Shelly Worker enumerations ==================================================
class StepKind(StrEnum):
    """Step kinds supported by the worker."""
    CHANGE_OUTPUT = "Change Output State"
    SLEEP = "Sleep"
    REFRESH_STATUS = "Refresh Status"
    GET_LOCATION = "Get Location"


STEP_TYPE_MAP = {
    "SLEEP": StepKind.SLEEP,
    "DELAY": StepKind.SLEEP,
    "CHANGE_OUTPUT": StepKind.CHANGE_OUTPUT,
    "REFRESH_STATUS": StepKind.REFRESH_STATUS,
    "GET_LOCATION": StepKind.GET_LOCATION,
}


@dataclass
class ShellyStep:
    kind: StepKind
    # CHANGE_OUTPUT: {"output_identity": "Label", "state": True|False}
    # SLEEP: {"seconds": float}
    # REFRESH_STATUS: {}
    # GET_LOCATION: {"device_identity": "Label"}
    params: dict[str, Any] = field(default_factory=dict)
    timeout_s: float | None = None
    retries: int = 0
    retry_backoff_s: float = 0.5


@dataclass
class ShellySequenceResult:
    id: str
    ok: bool
    error: str | None = None
    started_ts: float = field(default_factory=time.time)
    finished_ts: float = 0.0


@dataclass
class ShellySequenceRequest:
    steps: list[ShellyStep]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    label: str = ""
    timeout_s: float | None = None
    on_complete: Callable[[ShellySequenceResult], None] | None = None  # optional callback


@dataclass
class ShellyStatus:
    devices: list[dict]
    outputs: list[dict]
    inputs: list[dict]
    meters: list[dict]
    temp_probes: list[dict]


# Input and Output control enumerations =======================================
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
    output_type: str = "shelly"  # One of "shelly", "teslamate", "meter"


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
    request: ShellySequenceRequest | None
    type: OutputActionType
    system_state: SystemState
    reason: StateReasonOn | StateReasonOff


# Metered output usage =======================================
@dataclass
class UsageReportingPeriod:
    """Define a reporting period for metered output usage."""
    name: str
    start_date: dt.date
    end_date: dt.date
    have_global_data: bool = False
    global_energy_used: float = 0.0
    global_cost: float = 0.0
    output_energy_used: float = 0.0
    output_cost: float = 0.0
    other_energy_used: float = 0.0
    other_cost: float = 0.0
