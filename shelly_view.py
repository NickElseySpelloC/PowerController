from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ShellyView:
    """Read-only facade over a ShellyWorker snapshot.

    Exposes primitive getters by component name or device id.
    """
    snapshot: list[dict[str, Any]]

    # Declare internal indexes so type checkers know they exist
    _devices_by_id: dict[str, dict[str, Any]] = field(init=False, repr=False)
    _outputs_by_name: dict[str, dict[str, Any]] = field(init=False, repr=False)
    _meters_by_name: dict[str, dict[str, Any]] = field(init=False, repr=False)
    _inputs_by_name: dict[str, dict[str, Any]] = field(init=False, repr=False)
    _output2device: dict[str, str] = field(init=False, repr=False)

    def __post_init__(self):
        # Build simple indices for fast lookup by name and device id.
        object.__setattr__(self, "_devices_by_id", {})
        object.__setattr__(self, "_outputs_by_name", {})
        object.__setattr__(self, "_meters_by_name", {})
        object.__setattr__(self, "_inputs_by_name", {})
        object.__setattr__(self, "_output2device", {})

        devices_by_id: dict[str, dict[str, Any]] = {}
        outputs_by_name: dict[str, dict[str, Any]] = {}
        meters_by_name: dict[str, dict[str, Any]] = {}
        inputs_by_name: dict[str, dict[str, Any]] = {}
        output2device: dict[str, str] = {}

        # To DO: Review all this and make sure it follows the ShellgControl structure
        for dev in self.snapshot:
            dev_id = _first_key(dev, "DeviceID", "ID", "Id", "Mac", "MacAddress")
            if not dev_id:
                continue
            devices_by_id[dev_id] = dev

            # Components may be under "Components" (typed) or split lists
            comps = dev.get("Components") or []
            for comp in comps:
                ctype = comp.get("Type", "").lower()
                cname = comp.get("Name") or comp.get("Label")
                if not cname:
                    continue
                if ctype == "output":
                    outputs_by_name[cname] = comp
                    output2device[cname] = comp.get("DeviceID") or dev_id
                elif ctype == "meter":
                    meters_by_name[cname] = comp
                elif ctype == "input":
                    inputs_by_name[cname] = comp

            # Also accept split lists if present
            for comp in dev.get("Outputs", []) or []:
                cname = comp.get("Name") or comp.get("Label")
                if cname:
                    outputs_by_name[cname] = comp
                    output2device[cname] = comp.get("DeviceID") or dev_id
            for comp in dev.get("Meters", []) or []:
                cname = comp.get("Name") or comp.get("Label")
                if cname:
                    meters_by_name[cname] = comp
            for comp in dev.get("Inputs", []) or []:
                cname = comp.get("Name") or comp.get("Label")
                if cname:
                    inputs_by_name[cname] = comp

        object.__setattr__(self, "_devices_by_id", devices_by_id)
        object.__setattr__(self, "_outputs_by_name", outputs_by_name)
        object.__setattr__(self, "_meters_by_name", meters_by_name)
        object.__setattr__(self, "_inputs_by_name", inputs_by_name)
        object.__setattr__(self, "_output2device", output2device)

    # Output primitives
    def get_output_state(self, output_name: str) -> bool | None:
        comp = self._outputs_by_name.get(output_name)
        if not comp:
            return None
        return bool(comp.get("State", False))

    def get_output_device_id(self, output_name: str) -> str | None:
        return self._output2device.get(output_name)

    # Device primitives
    def get_device_online(self, device_id: str) -> bool | None:
        dev = self._devices_by_id.get(device_id)
        if not dev:
            return None
        return bool(dev.get("Online", False))

    def get_device_name(self, device_id: str) -> str | None:
        dev = self._devices_by_id.get(device_id)
        return None if not dev else (dev.get("Name") or dev.get("Label"))

    def get_device_client_name(self, device_id: str) -> str | None:
        dev = self._devices_by_id.get(device_id)
        return None if not dev else dev.get("ClientName")

    def get_device_expect_offline(self, device_id: str) -> bool:
        dev = self._devices_by_id.get(device_id)
        if not dev:
            return False
        return bool(dev.get("ExpectOffline", False))

    def get_device_online_for_output(self, output_name: str) -> bool | None:
        dev_id = self.get_output_device_id(output_name)
        return None if not dev_id else self.get_device_online(dev_id)
    
    def all_devices_online(self) -> bool:
        for dev in self._devices_by_id.values():
            if not dev.get("Online", False):
                return False
        return True

    # Meter primitives
    def get_meter_energy(self, meter_name: str) -> float:
        comp = self._meters_by_name.get(meter_name)
        if not comp:
            return 0.0
        # Wh or kWh depends on source; your code expects Wh in RunHistory
        val = comp.get("Energy") or 0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    def get_meter_power(self, meter_name: str) -> float:
        comp = self._meters_by_name.get(meter_name)
        if not comp:
            return 0.0
        val = comp.get("Power", 0) or 0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    # Input primitives
    def get_input_state(self, input_name: str) -> bool | None:
        comp = self._inputs_by_name.get(input_name)
        if not comp:
            return None
        return bool(comp.get("State", False))


def _first_key(d: dict[str, Any], *keys: str) -> str | None:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v:
            return v
    return None
