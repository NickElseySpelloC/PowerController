"""Tests for ShellyView — the read-only facade over a ShellyStatus snapshot."""

import sys
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from local_enumerations import ShellyStatus
from shelly_view import ShellyView

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_view(
    num_devices: int = 1,
    device_online: bool = True,
    output_state: bool = False,
    temp_probe_temp: float | None = 22.5,
) -> ShellyView:
    devices = [
        {"ID": i, "Name": f"Device {i}", "Online": device_online, "ExpectOffline": False, "Temperature": 40.0}
        for i in range(1, num_devices + 1)
    ]
    outputs = [
        {"ID": i, "Name": f"Output {i}", "DeviceID": 1, "State": output_state}
        for i in range(1, 3)
    ]
    inputs = [
        {"ID": i, "Name": f"Input {i}", "DeviceID": 1, "State": False}
        for i in range(1, 3)
    ]
    meters = [
        {"ID": i, "Name": f"Meter {i}", "DeviceID": 1, "Energy": 100.0 * i, "Power": 50.0 * i}
        for i in range(1, 3)
    ]
    temp_probes = [
        {"ID": 1, "Name": "Probe A", "DeviceID": 1, "Temperature": temp_probe_temp}
    ]
    status = ShellyStatus(
        devices=devices, outputs=outputs, inputs=inputs,
        meters=meters, temp_probes=temp_probes,
    )
    return ShellyView(snapshot=status)


def _empty_view() -> ShellyView:
    return ShellyView(snapshot=ShellyStatus(devices=[], outputs=[], inputs=[], meters=[], temp_probes=[]))


# ---------------------------------------------------------------------------
# Construction & indices
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_view_built_from_status(self):
        view = _build_view()
        assert view.snapshot is not None

    def test_empty_snapshot_does_not_raise(self):
        view = _empty_view()
        assert view.get_device_id_list() == []


# ---------------------------------------------------------------------------
# Device lookups
# ---------------------------------------------------------------------------

class TestDeviceLookups:
    def test_get_device_id_by_name(self):
        view = _build_view()
        assert view.get_device_id("Device 1") == 1

    def test_get_device_id_unknown_name_returns_zero(self):
        view = _build_view()
        assert view.get_device_id("NonExistent") == 0

    def test_get_device_id_list(self):
        view = _build_view(num_devices=2)
        ids = view.get_device_id_list()
        assert 1 in ids
        assert 2 in ids

    def test_validate_device_id_by_int(self):
        view = _build_view()
        assert view.validate_device_id(1) is True
        assert view.validate_device_id(999) is False

    def test_validate_device_id_by_string_name(self):
        view = _build_view()
        assert view.validate_device_id("Device 1") is True
        assert view.validate_device_id("NoSuch") is False

    def test_get_device_online_true(self):
        view = _build_view(device_online=True)
        assert view.get_device_online(1) is True

    def test_get_device_online_false(self):
        view = _build_view(device_online=False)
        assert view.get_device_online(1) is False

    def test_get_device_online_invalid_id_raises(self):
        view = _build_view()
        with pytest.raises(IndexError):
            view.get_device_online(999)

    def test_get_device_name(self):
        view = _build_view()
        assert view.get_device_name(1) == "Device 1"

    def test_get_device_name_invalid_id_raises(self):
        view = _build_view()
        with pytest.raises(IndexError):
            view.get_device_name(999)

    def test_get_device_expect_offline(self):
        view = _build_view()
        assert view.get_device_expect_offline(1) is False

    def test_get_device_temperature(self):
        view = _build_view()
        assert view.get_device_temperature(1) == pytest.approx(40.0)

    def test_all_devices_online_all_up(self):
        view = _build_view(num_devices=2, device_online=True)
        assert view.all_devices_online() is True

    def test_all_devices_online_one_down(self):
        status = ShellyStatus(
            devices=[
                {"ID": 1, "Name": "D1", "Online": True, "ExpectOffline": False, "Temperature": None},
                {"ID": 2, "Name": "D2", "Online": False, "ExpectOffline": False, "Temperature": None},
            ],
            outputs=[], inputs=[], meters=[], temp_probes=[],
        )
        view = ShellyView(snapshot=status)
        assert view.all_devices_online() is False


# ---------------------------------------------------------------------------
# Output lookups
# ---------------------------------------------------------------------------

class TestOutputLookups:
    def test_get_output_id_by_name(self):
        view = _build_view()
        assert view.get_output_id("Output 1") == 1

    def test_get_output_id_unknown_returns_zero(self):
        view = _build_view()
        assert view.get_output_id("NoSuch") == 0

    def test_validate_output_id_by_int(self):
        view = _build_view()
        assert view.validate_output_id(1) is True
        assert view.validate_output_id(999) is False

    def test_validate_output_id_by_string(self):
        view = _build_view()
        assert view.validate_output_id("Output 1") is True
        assert view.validate_output_id("NoSuch") is False

    def test_get_output_state_when_device_online(self):
        view = _build_view(device_online=True, output_state=True)
        assert view.get_output_state(1) is True

    def test_get_output_state_false_when_device_offline(self):
        """Output always reports off when device is offline."""
        view = _build_view(device_online=False, output_state=True)
        assert view.get_output_state(1) is False

    def test_get_output_state_invalid_id_raises(self):
        view = _build_view()
        with pytest.raises(IndexError):
            view.get_output_state(999)

    def test_get_output_device_id(self):
        view = _build_view()
        device_id = view.get_output_device_id(1)
        assert device_id == 1

    def test_get_output_device_id_invalid_raises(self):
        view = _build_view()
        with pytest.raises(IndexError):
            view.get_output_device_id(999)


# ---------------------------------------------------------------------------
# Input lookups
# ---------------------------------------------------------------------------

class TestInputLookups:
    def test_get_input_id_by_name(self):
        view = _build_view()
        assert view.get_input_id("Input 1") == 1

    def test_get_input_id_unknown_returns_zero(self):
        view = _build_view()
        assert view.get_input_id("NoSuch") == 0

    def test_get_input_state(self):
        view = _build_view()
        assert view.get_input_state(1) is False

    def test_get_input_state_invalid_raises(self):
        view = _build_view()
        with pytest.raises(IndexError):
            view.get_input_state(999)


# ---------------------------------------------------------------------------
# Meter lookups
# ---------------------------------------------------------------------------

class TestMeterLookups:
    def test_get_meter_id_by_name(self):
        view = _build_view()
        assert view.get_meter_id("Meter 1") == 1

    def test_get_meter_id_unknown_returns_zero(self):
        view = _build_view()
        assert view.get_meter_id("NoSuch") == 0

    def test_get_meter_energy(self):
        view = _build_view()
        assert view.get_meter_energy(1) == pytest.approx(100.0)

    def test_get_meter_power(self):
        view = _build_view()
        assert view.get_meter_power(1) == pytest.approx(50.0)

    def test_get_meter_energy_invalid_raises(self):
        view = _build_view()
        with pytest.raises(IndexError):
            view.get_meter_energy(999)

    def test_get_meter_power_invalid_raises(self):
        view = _build_view()
        with pytest.raises(IndexError):
            view.get_meter_power(999)


# ---------------------------------------------------------------------------
# Temperature probe lookups
# ---------------------------------------------------------------------------

class TestTempProbeLookups:
    def test_get_temp_probe_id_by_name(self):
        view = _build_view()
        assert view.get_temp_probe_id("Probe A") == 1

    def test_get_temp_probe_id_unknown_returns_zero(self):
        view = _build_view()
        assert view.get_temp_probe_id("NoSuch") == 0

    def test_get_temp_probe_temperature(self):
        view = _build_view(temp_probe_temp=23.5)
        assert view.get_temp_probe_temperature(1) == pytest.approx(23.5)

    def test_get_temp_probe_temperature_none_when_null(self):
        view = _build_view(temp_probe_temp=None)
        assert view.get_temp_probe_temperature(1) is None


# ---------------------------------------------------------------------------
# JSON snapshot
# ---------------------------------------------------------------------------

class TestJsonSnapshot:
    def test_snapshot_has_expected_keys(self):
        view = _build_view()
        snap = view.get_json_snapshot()
        assert "devices" in snap
        assert "outputs" in snap
        assert "inputs" in snap
        assert "meters" in snap
        assert "temp_probes" in snap
