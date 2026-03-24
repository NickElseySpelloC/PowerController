"""Tests for UPSIntegration — UPS health monitoring and status reporting."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ups_integration import UPSIntegration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_logger():
    m = MagicMock()
    m.log_message = MagicMock()
    return m


def _make_config(enable: bool = True, devices: list | None = None):
    """Build a mock SCConfigManager that returns a UPSIntegration config."""
    cfg = MagicMock()
    ups_conf = {
        "Enable": enable,
        "PollingInterval": 30,
        "DataFile": None,
        "DataFileWriteInterval": 60,
        "DataFileMaxDays": 3,
        "UPSDevices": devices or [],
    }

    def _get(*keys, default=None):
        if keys == ("UPSIntegration",):
            return ups_conf if enable else {"Enable": False}
        return default

    cfg.get.side_effect = _get
    return cfg


def _make_ups(enable=True, devices=None) -> UPSIntegration:
    return UPSIntegration(_make_config(enable=enable, devices=devices), _make_logger())


def _ups_entry(
    name="APC UPS",
    script="echo '{}'",
    battery_state=None,
    charge=None,
    runtime=None,
    min_charge_charging=80,
    min_charge_discharging=10,
    min_runtime_charging=0,
    min_runtime_discharging=0,
) -> dict:
    return {
        "name": name,
        "script": script,
        "battery_state": battery_state,
        "battery_charge_percent": charge,
        "battery_runtime_seconds": runtime,
        "min_charge_when_charging": min_charge_charging,
        "min_charge_when_discharging": min_charge_discharging,
        "min_runtime_when_charging": min_runtime_charging,
        "min_runtime_when_discharging": min_runtime_discharging,
        "timestamp": None,
        "is_healthy": True,
    }


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestInitialisation:
    def test_disabled_config_results_in_empty_ups_list(self):
        ups = _make_ups(enable=False)
        assert ups.enabled is False
        assert ups.ups_list == []

    def test_enabled_with_no_devices(self):
        ups = _make_ups(enable=True, devices=[])
        assert ups.enabled is True
        assert ups.ups_list == []

    def test_enabled_with_one_device(self):
        devices = [{"Name": "APC UPS", "Script": "echo '{}'"}]
        ups = _make_ups(enable=True, devices=devices)
        assert len(ups.ups_list) == 1
        assert ups.ups_list[0]["name"] == "APC UPS"

    def test_device_missing_name_skipped(self):
        devices = [{"Script": "echo '{}'"}]  # missing Name
        ups = _make_ups(enable=True, devices=devices)
        assert ups.ups_list == []

    def test_device_missing_script_skipped(self):
        devices = [{"Name": "APC UPS"}]  # missing Script
        ups = _make_ups(enable=True, devices=devices)
        assert ups.ups_list == []


# ---------------------------------------------------------------------------
# is_ups_healthy — before any reading
# ---------------------------------------------------------------------------

class TestIsUpsHealthyBeforeReading:
    def test_no_reading_yet_returns_true(self):
        devices = [{"Name": "APC UPS", "Script": "echo '{}'"}]
        ups = _make_ups(enable=True, devices=devices)
        assert ups.is_ups_healthy("APC UPS") is True

    def test_disabled_ups_always_healthy(self):
        ups = _make_ups(enable=False)
        # When disabled, is_ups_healthy always returns True
        assert ups.is_ups_healthy.__func__ is not None  # sanity
        result = ups.is_ups_healthy("Any UPS")
        assert result is True

    def test_unknown_ups_name_raises(self):
        devices = [{"Name": "APC UPS", "Script": "echo '{}'"}]
        ups = _make_ups(enable=True, devices=devices)
        with pytest.raises(RuntimeError, match="not found in configuration"):
            ups.is_ups_healthy("NonExistent UPS")


# ---------------------------------------------------------------------------
# get_ups_results
# ---------------------------------------------------------------------------

class TestGetUpsResults:
    def test_disabled_returns_empty_dict(self):
        ups = _make_ups(enable=False)
        assert ups.get_ups_results() == {}

    def test_returns_all_ups_when_no_name(self):
        devices = [
            {"Name": "UPS 1", "Script": "echo '{}'"},
            {"Name": "UPS 2", "Script": "echo '{}'"},
        ]
        ups = _make_ups(enable=True, devices=devices)
        result = ups.get_ups_results()
        assert "UPS 1" in result
        assert "UPS 2" in result

    def test_returns_specific_ups_by_name(self):
        devices = [{"Name": "APC UPS", "Script": "echo '{}'"}]
        ups = _make_ups(enable=True, devices=devices)
        result = ups.get_ups_results("APC UPS")
        assert "APC UPS" in result
        entry = result["APC UPS"]
        assert "timestamp" in entry
        assert "battery_charge_percent" in entry
        assert "is_healthy" in entry

    def test_unknown_name_raises(self):
        devices = [{"Name": "APC UPS", "Script": "echo '{}'"}]
        ups = _make_ups(enable=True, devices=devices)
        with pytest.raises(RuntimeError, match="not found in configuration"):
            ups.get_ups_results("NonExistent")


# ---------------------------------------------------------------------------
# _update_ups_health_status
# ---------------------------------------------------------------------------

class TestUpdateUpsHealthStatus:
    """Unit tests for the health status logic, bypassing subprocess execution."""

    def _check(self, ups_entry: dict) -> bool:
        """Run the health check and return the result."""
        devices = [{"Name": ups_entry["name"], "Script": "echo '{}'",
                    "MinChargeWhenCharging": ups_entry.get("min_charge_when_charging", 0),
                    "MinChargeWhenDischarging": ups_entry.get("min_charge_when_discharging", 0),
                    "MinRuntimeWhenCharging": ups_entry.get("min_runtime_when_charging", 0),
                    "MinRuntimeWhenDischarging": ups_entry.get("min_runtime_when_discharging", 0)}]
        ups = _make_ups(enable=True, devices=devices)
        # Directly update the ups_entry in the ups_list to match our scenario
        ups.ups_list[0].update(ups_entry)
        ups._update_ups_health_status(ups.ups_list[0])
        return ups.ups_list[0]["is_healthy"]

    def test_charged_always_healthy(self):
        entry = _ups_entry(battery_state="charged", charge=100, runtime=3600)
        assert self._check(entry) is True

    def test_charged_ignores_low_charge(self):
        """Even with charge below threshold, 'charged' state is always healthy."""
        entry = _ups_entry(battery_state="charged", charge=5, runtime=60,
                           min_charge_charging=80)
        assert self._check(entry) is True

    def test_no_data_is_healthy(self):
        entry = _ups_entry(battery_state=None, charge=None, runtime=None)
        assert self._check(entry) is True

    # Charging scenarios
    def test_charging_above_min_charge_is_healthy(self):
        entry = _ups_entry(battery_state="charging", charge=90, runtime=3600,
                           min_charge_charging=80)
        assert self._check(entry) is True

    def test_charging_below_min_charge_is_unhealthy(self):
        entry = _ups_entry(battery_state="charging", charge=60, runtime=3600,
                           min_charge_charging=80)
        assert self._check(entry) is False

    def test_charging_below_min_runtime_is_unhealthy(self):
        entry = _ups_entry(battery_state="charging", charge=90, runtime=100,
                           min_charge_charging=80, min_runtime_charging=600)
        assert self._check(entry) is False

    def test_charging_zero_thresholds_is_healthy(self):
        """When thresholds are 0, any charge/runtime is healthy."""
        entry = _ups_entry(battery_state="charging", charge=1, runtime=1,
                           min_charge_charging=0, min_runtime_charging=0)
        assert self._check(entry) is True

    # Discharging scenarios
    def test_discharging_above_min_charge_is_healthy(self):
        entry = _ups_entry(battery_state="discharging", charge=50, runtime=600,
                           min_charge_discharging=10)
        assert self._check(entry) is True

    def test_discharging_below_min_charge_is_unhealthy(self):
        entry = _ups_entry(battery_state="discharging", charge=5, runtime=600,
                           min_charge_discharging=10)
        assert self._check(entry) is False

    def test_discharging_below_min_runtime_is_unhealthy(self):
        entry = _ups_entry(battery_state="discharging", charge=50, runtime=60,
                           min_charge_discharging=10, min_runtime_discharging=300)
        assert self._check(entry) is False

    def test_discharging_both_thresholds_violated_is_unhealthy(self):
        entry = _ups_entry(battery_state="discharging", charge=5, runtime=60,
                           min_charge_discharging=10, min_runtime_discharging=300)
        assert self._check(entry) is False

    def test_discharging_zero_thresholds_is_healthy(self):
        entry = _ups_entry(battery_state="discharging", charge=1, runtime=1,
                           min_charge_discharging=0, min_runtime_discharging=0)
        assert self._check(entry) is True
