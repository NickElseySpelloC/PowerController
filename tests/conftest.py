"""Shared pytest fixtures for the PowerController test suite."""

import sys
import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# Ensure src/ is importable without PYTHONPATH being set
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config_schemas import ConfigSchema
from sc_utility import SCConfigManager, SCLogger
from scheduler import Scheduler
from ups_integration import UPSIntegration

from local_enumerations import ShellyStatus
from shelly_view import ShellyView
from shelly_worker import ShellyWorker

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_CONFIG = str(PROJECT_ROOT / "configs" / "testing.yaml")


# ---------------------------------------------------------------------------
# Core infrastructure fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def logger() -> SCLogger:
    """Return a silent logger (no file, errors only on console)."""
    return SCLogger({
        "logfile_name": None,
        "console_verbosity": "error",
    })


@pytest.fixture(scope="session")
def config() -> SCConfigManager:
    """Return the test SCConfigManager loaded from configs/testing.yaml."""
    schema = ConfigSchema()
    return SCConfigManager(
        config_file=TEST_CONFIG,
        validation_schema=schema.validation,
        placeholders=schema.placeholders,
    )


@pytest.fixture(scope="session")
def scheduler(config, logger):
    """Return a Scheduler built from the test config."""
    return Scheduler(config, logger)


@pytest.fixture(scope="session")
def ups_integration(config, logger):
    """Return an UPSIntegration built from the test config (disabled)."""
    return UPSIntegration(config, logger)


# ---------------------------------------------------------------------------
# Shelly simulation fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def shelly_worker(config, logger) -> ShellyWorker:
    """Return a ShellyWorker using simulated devices. Worker thread not started."""
    wake_event = threading.Event()
    worker = ShellyWorker(config, logger, wake_event)
    return worker


@pytest.fixture(scope="session")
def shelly_view(shelly_worker) -> ShellyView:
    """Return a ShellyView built from the simulated worker's initial snapshot."""
    status = shelly_worker.get_latest_status()
    return ShellyView(snapshot=status)


# ---------------------------------------------------------------------------
# Synthetic ShellyView builder (for unit tests that need full control)
# ---------------------------------------------------------------------------

def make_shelly_status(
    device_online: bool = True,
    output_state: bool = False,
    device_id: int = 1,
    output_id: int = 1,
    input_id: int = 1,
    meter_id: int = 1,
    temp_probe_id: int = 1,
    temp_probe_temp: float | None = 25.0,
) -> ShellyStatus:
    """Build a minimal ShellyStatus for unit tests."""
    return ShellyStatus(
        devices=[{
            "ID": device_id,
            "Name": "Test Device",
            "Online": device_online,
            "ExpectOffline": False,
            "Temperature": None,
        }],
        outputs=[{
            "ID": output_id,
            "Name": "Network Rack O1",
            "DeviceID": device_id,
            "State": output_state,
        }],
        inputs=[{
            "ID": input_id,
            "Name": "Input 1",
            "DeviceID": device_id,
            "State": False,
        }],
        meters=[{
            "ID": meter_id,
            "Name": "Meter 1",
            "DeviceID": device_id,
            "Energy": 0.0,
            "Power": 0.0,
        }],
        temp_probes=[{
            "ID": temp_probe_id,
            "Name": "Network Rack",
            "DeviceID": device_id,
            "Temperature": temp_probe_temp,
        }],
    )


@pytest.fixture
def synthetic_view() -> ShellyView:
    """Return a ShellyView built from minimal synthetic data (device online, output off)."""
    return ShellyView(snapshot=make_shelly_status())


# ---------------------------------------------------------------------------
# Mock controller factory (for DataAPI / webapp tests)
# ---------------------------------------------------------------------------

def make_mock_controller(api_data: dict | None = None, webapp_data: dict | None = None) -> Any:
    """Return a MagicMock controller that returns supplied data from its API methods."""
    ctrl = MagicMock()
    ctrl.get_api_data.return_value = api_data or {"LastRefresh": "2025-01-01T00:00:00"}
    ctrl.get_webapp_data.return_value = webapp_data or {
        "global": {"label": "Test"},
        "outputs": {},
    }
    ctrl.is_valid_output_id.return_value = True
    ctrl.post_command.return_value = None
    return ctrl
