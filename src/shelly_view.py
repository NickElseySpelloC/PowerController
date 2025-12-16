from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import datetime as dt

    from shelly_worker import ShellyStatus


@dataclass(frozen=True)  # noqa: PLR0904
class ShellyView:
    """Read-only facade over a ShellyStatus snapshot.

    Provides efficient ID-based lookups for all component types.
    Each component type has a name->ID mapping and ID-based value getters.
    """
    snapshot: ShellyStatus

    # Internal indices: name -> ID mappings
    _device_name_to_id: dict[str, int] = field(init=False, repr=False)
    _output_name_to_id: dict[str, int] = field(init=False, repr=False)
    _input_name_to_id: dict[str, int] = field(init=False, repr=False)
    _meter_name_to_id: dict[str, int] = field(init=False, repr=False)
    _temp_probe_name_to_id: dict[str, int] = field(init=False, repr=False)

    # Internal indices: ID -> dict mappings
    _devices_by_id: dict[int, dict[str, Any]] = field(init=False, repr=False)
    _outputs_by_id: dict[int, dict[str, Any]] = field(init=False, repr=False)
    _inputs_by_id: dict[int, dict[str, Any]] = field(init=False, repr=False)
    _meters_by_id: dict[int, dict[str, Any]] = field(init=False, repr=False)
    _temp_probes_by_id: dict[int, dict[str, Any]] = field(init=False, repr=False)

    def __post_init__(self):
        """Build name->ID and ID->dict indices for fast lookups."""
        object.__setattr__(self, "_device_name_to_id", self._build_name_index(self.snapshot.devices))
        object.__setattr__(self, "_output_name_to_id", self._build_name_index(self.snapshot.outputs))
        object.__setattr__(self, "_input_name_to_id", self._build_name_index(self.snapshot.inputs))
        object.__setattr__(self, "_meter_name_to_id", self._build_name_index(self.snapshot.meters))
        object.__setattr__(self, "_temp_probe_name_to_id", self._build_name_index(self.snapshot.temp_probes))

        object.__setattr__(self, "_devices_by_id", self._build_id_index(self.snapshot.devices))
        object.__setattr__(self, "_outputs_by_id", self._build_id_index(self.snapshot.outputs))
        object.__setattr__(self, "_inputs_by_id", self._build_id_index(self.snapshot.inputs))
        object.__setattr__(self, "_meters_by_id", self._build_id_index(self.snapshot.meters))
        object.__setattr__(self, "_temp_probes_by_id", self._build_id_index(self.snapshot.temp_probes))

    @staticmethod
    def _build_name_index(items: list[dict[str, Any]]) -> dict[str, int]:
        """Build a name->ID mapping from a list of component dicts.

        Args:
            items: List of component dictionaries with Name and ID keys.

        Returns:
            Mapping from component name to ID.
        """
        return {item["Name"]: item["ID"] for item in items}

    @staticmethod
    def _build_id_index(items: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        """Build an ID->dict mapping from a list of component dicts.

        Args:
            items: List of component dictionaries with Name and ID keys.

        Returns:
            Mapping from component ID to component dictionary.
        """
        return {item["ID"]: item for item in items}

    # Name lookup methods - return None if not found
    def validate_device_id(self, device_id: int | str) -> bool:
        """Validate if an device ID exists.

        Args:
            device_id: Device ID (int) or name (str) to validate.

        Returns:
            True if device ID/name exists, False otherwise.
        """
        if isinstance(device_id, str):
            # If it's a string, try to look up by name first
            resolved_id = self.get_device_id(device_id)
            return resolved_id != 0
        # If it's not a string, try to convert to int and check ID
        try:
            device_id_int = int(device_id)
        except (ValueError, TypeError):
            return False
        return device_id_int in self._devices_by_id

    def get_device_id_list(self) -> list[int]:
        """Get a list of all device IDs.

        Returns:
            List of device IDs.
        """
        return list(self._devices_by_id.keys())

    def get_device_id(self, name: str) -> int:
        """Get device ID by name.

        Args:
            name: Device name to lookup.

        Returns:
            Device ID, or 0 if not found.
        """
        return self._device_name_to_id.get(name, 0)

    def get_output_id(self, name: str) -> int:
        """Get output ID by name.

        Args:
            name: Output name to lookup.

        Returns:
            Output ID, or 0 if not found.
        """
        return self._output_name_to_id.get(name, 0)

    def get_input_id(self, name: str) -> int:
        """Get input ID by name.

        Args:
            name: Input name to lookup.

        Returns:
            Input ID, or 0 if not found.
        """
        return self._input_name_to_id.get(name, 0)

    def get_meter_id(self, name: str) -> int:
        """Get meter ID by name.

        Args:
            name: Meter name to lookup.

        Returns:
            Meter ID, or 0 if not found.
        """
        return self._meter_name_to_id.get(name, 0)

    def get_temp_probe_id(self, name: str) -> int:
        """Get temperature probe ID by name.

        Args:
            name: Temperature probe name to lookup.

        Returns:
            Temperature probe ID, or 0 if not found.
        """
        return self._temp_probe_name_to_id.get(name, 0)

    # Device value getters
    def get_device_online(self, device_id: int) -> bool:
        """Get device online status by ID.

        Args:
            device_id: Device ID to lookup.

        Returns:
            True if device is online, False otherwise.

        Raises:
            IndexError: If device_id is invalid.
        """
        if device_id not in self._devices_by_id:
            error_msg = f"Invalid device ID: {device_id}"
            raise IndexError(error_msg)
        return bool(self._devices_by_id[device_id].get("Online", False))

    def get_device_name(self, device_id: int) -> str:
        """Get device name by ID.

        Args:
            device_id: Device ID to lookup.

        Returns:
            Device name.

        Raises:
            IndexError: If device_id is invalid.
        """
        if device_id not in self._devices_by_id:
            error_msg = f"Invalid device ID: {device_id}"
            raise IndexError(error_msg)
        return str(self._devices_by_id[device_id]["Name"])

    def get_device_expect_offline(self, device_id: int) -> bool:
        """Get device expect_offline flag by ID.

        Args:
            device_id: Device ID to lookup.

        Returns:
            True if device is expected to be offline, False otherwise.

        Raises:
            IndexError: If device_id is invalid.
        """
        if device_id not in self._devices_by_id:
            error_msg = f"Invalid device ID: {device_id}"
            raise IndexError(error_msg)
        return bool(self._devices_by_id[device_id].get("ExpectOffline", False))

    def get_device_temperature(self, device_id: int) -> float | None:
        """Get device internal temperature in Celsius by ID.

        Args:
            device_id: Device ID to lookup.

        Returns:
            Temperature in Celsius, or None if unavailable.

        Raises:
            IndexError: If device_id is invalid.
        """
        if device_id not in self._devices_by_id:
            error_msg = f"Invalid device ID: {device_id}"
            raise IndexError(error_msg)
        val = self._devices_by_id[device_id].get("Temperature")
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def all_devices_online(self) -> bool:
        """Check if all devices are online.

        Returns:
            True if all devices are online, False otherwise.
        """
        return all(dev.get("Online", False) for dev in self._devices_by_id.values())

    def get_json_snapshot(self) -> dict[str, Any]:
        """Get the full JSON snapshot of the Shelly status.

        Returns:
            The snapshot as a dictionary.
        """
        return {
            "devices": self.snapshot.devices,
            "outputs": self.snapshot.outputs,
            "inputs": self.snapshot.inputs,
            "meters": self.snapshot.meters,
            "temp_probes": self.snapshot.temp_probes,
        }

    # Output value getters
    def validate_output_id(self, output_id: int | str) -> bool:
        """Validate if an output ID exists.

        Args:
            output_id: Output ID (int) or name (str) to validate.

        Returns:
            True if output ID/name exists, False otherwise.
        """
        if isinstance(output_id, str):
            # If it's a string, try to look up by name first
            resolved_id = self.get_output_id(output_id)
            return resolved_id != 0
        # If it's not a string, try to convert to int and check ID
        try:
            output_id_int = int(output_id)
        except (ValueError, TypeError):
            return False
        return output_id_int in self._outputs_by_id

    def get_output_state(self, output_id: int) -> bool:
        """Get output state by ID.

        Args:
            output_id: Output ID to lookup.

        Returns:
            True if output is on, False if off.

        Raises:
            IndexError: If output_id is invalid.
        """
        if output_id not in self._outputs_by_id:
            error_msg = f"Invalid output ID: {output_id}"
            raise IndexError(error_msg)

        # If the device is offline, output is off by definition
        device_id = self.get_output_device_id(output_id)
        if not self.get_device_online(device_id):
            return False
        return bool(self._outputs_by_id[output_id].get("State", False))

    def get_output_device_id(self, output_id: int) -> int:
        """Get the device ID that owns this output.

        Args:
            output_id: Output ID to lookup.

        Returns:
            Device ID that owns this output.

        Raises:
            IndexError: If output_id is invalid.
        """
        if output_id not in self._outputs_by_id:
            error_msg = f"Invalid output ID: {output_id}"
            raise IndexError(error_msg)
        return int(self._outputs_by_id[output_id].get("DeviceID", 0))

    # Input value getters
    def get_input_state(self, input_id: int) -> bool:
        """Get input state by ID.

        Args:
            input_id: Input ID to lookup.

        Returns:
            True if input is active, False otherwise.

        Raises:
            IndexError: If input_id is invalid.
        """
        if input_id not in self._inputs_by_id:
            error_msg = f"Invalid input ID: {input_id}"
            raise IndexError(error_msg)
        return bool(self._inputs_by_id[input_id].get("State", False))

    # Meter value getters
    def get_meter_energy(self, meter_id: int) -> float:
        """Get meter energy reading (Wh) by ID.

        Args:
            meter_id: Meter ID to lookup.

        Returns:
            Energy reading in Wh, or 0.0 if unavailable.

        Raises:
            IndexError: If meter_id is invalid.
        """
        if meter_id not in self._meters_by_id:
            error_msg = f"Invalid meter ID: {meter_id}"
            raise IndexError(error_msg)
        val = self._meters_by_id[meter_id].get("Energy", 0) or 0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    def get_meter_power(self, meter_id: int) -> float:
        """Get meter power reading (W) by ID.

        Args:
            meter_id: Meter ID to lookup.

        Returns:
            Power reading in W, or 0.0 if unavailable.

        Raises:
            IndexError: If meter_id is invalid.
        """
        if meter_id not in self._meters_by_id:
            error_msg = f"Invalid meter ID: {meter_id}"
            raise IndexError(error_msg)
        val = self._meters_by_id[meter_id].get("Power", 0) or 0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    # Temperature probe value getters
    def get_temp_probe_temperature(self, temp_probe_id: int) -> float | None:
        """Get temperature probe reading (°C) by ID.

        Args:
            temp_probe_id: Temperature probe ID to lookup.

        Returns:
            Temperature in °C, or None if unavailable.

        Raises:
            IndexError: If temp_probe_id is invalid.
        """
        if temp_probe_id not in self._temp_probes_by_id:
            error_msg = f"Invalid temperature probe ID: {temp_probe_id}"
            raise IndexError(error_msg)
        val = self._temp_probes_by_id[temp_probe_id].get("Temperature")
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def get_temp_probe_reading_time(self, temp_probe_id: int) -> dt.datetime | None:
        """Get temperature probe reading (°C) by ID.

        Args:
            temp_probe_id: Temperature probe ID to lookup.

        Returns:
            Temperature in °C, or None if unavailable.

        Raises:
            IndexError: If temp_probe_id is invalid.
        """
        if temp_probe_id not in self._temp_probes_by_id:
            error_msg = f"Invalid temperature probe ID: {temp_probe_id}"
            raise IndexError(error_msg)
        val = self._temp_probes_by_id[temp_probe_id].get("LastReadingTime")
        if val is None:
            return None
        try:
            return val
        except (ValueError, TypeError):
            return None
