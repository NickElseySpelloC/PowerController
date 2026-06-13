"""Helper class for evaluating output constraints."""
from sc_foundation import DateHelper, SCLogger
from sc_smart_device import SmartDeviceView

from local_enumerations import UPSMode
from ups_integration import UPSIntegration


class OutputConstraint:
    """Evaluates constraint conditions for an output device."""

    def __init__(self, output_config: dict, name: str, logger: SCLogger, ups_integration: UPSIntegration, device_output_id: int, view: SmartDeviceView):
        self.output_config = output_config
        self.name = name
        self.logger = logger
        self.ups_integration = ups_integration
        self.device_output_id = device_output_id

        self.dates_off: list[dict] = []
        dates_off_list = output_config.get("DatesOff", [])
        for date_range in dates_off_list:
            start_date = date_range.get("StartDate")
            end_date = date_range.get("EndDate")
            if not start_date or not end_date:
                raise RuntimeError(f"Invalid date range in DatesOff for output {name}.")
            self.dates_off.append({"StartDate": start_date, "EndDate": end_date})

        self.temp_probe_constraints: list[dict[str, str | int | float]] = []
        for constraint in output_config.get("TempProbeConstraints", []):
            temp_probe_name = constraint.get("TempProbe")
            condition = constraint.get("Condition")
            temperature = constraint.get("Temperature")
            fall_back_temp = constraint.get("FallBackTemp")
            if not temp_probe_name or condition not in {"GreaterThan", "LessThan"} or not isinstance(temperature, (int, float)):
                raise RuntimeError(f"Invalid TempProbeConstraint in output {name}.")
            temp_probe_id = view.get_temp_probe_id(temp_probe_name)
            if not temp_probe_id:
                raise RuntimeError(f"TempProbe {temp_probe_name} not found for output {name}.")
            if condition == "GreaterThan" and fall_back_temp and fall_back_temp >= temperature:
                raise RuntimeError(f"Invalid FallBackTemp for TempProbeConstraint in output {name}. For a GreaterThan constraint, FallBackTemp must be less than the main Temperature.")
            if condition == "LessThan" and fall_back_temp and fall_back_temp <= temperature:
                raise RuntimeError(f"Invalid FallBackTemp for TempProbeConstraint in output {name}. For a LessThan constraint, FallBackTemp must be greater than the main Temperature.")
            constraint["ProbeID"] = temp_probe_id
            self.temp_probe_constraints.append(constraint)

    def get_dates_off(self) -> list[dict]:
        """Return the parsed DatesOff list."""
        return self.dates_off

    def is_today_excluded(self) -> bool:
        """Check if today falls within any specified DatesOff range which states that the output should be off.

        Returns:
            result(bool): True if today is excluded, False otherwise.
        """
        today = DateHelper.today()
        for rng in self.dates_off:
            if rng["StartDate"] <= today <= rng["EndDate"]:
                return True
        return False

    def get_ups_health_status(self) -> UPSMode:
        """Get the current UPS health status.

        Returns:
            UPSMode: The current UPS health status.
        """
        if not self.ups_integration:
            return UPSMode.AUTO

        ups_config = self.output_config.get("UPSIntegration", {})
        if not ups_config:
            return UPSMode.AUTO

        ups_name = ups_config.get("UPS")
        ups_action = ups_config.get("ActionIfUnhealthy")
        if not ups_name or not ups_action or ups_action not in {"TurnOff", "TurnOn"}:
            self.logger.log_message(f"Output {self.name} has an invalid UPSIntegration configuration. UPS and ActionIfUnhealthy are required. Defaulting to AUTO mode.", "error")
            return UPSMode.AUTO

        try:
            ups_status = self.ups_integration.is_ups_healthy(ups_name)
        except RuntimeError as e:
            self.logger.log_message(f"Error checking UPS status for {self.name}: {e}", "error")
            return UPSMode.AUTO
        else:
            if not ups_status and ups_action == "TurnOff":
                self.logger.log_message(f"UPS {ups_name} is unhealthy. Output {self.name} will turn OFF based on UPSIntegration configuration.", "debug")
                return UPSMode.TURN_OFF
            if not ups_status and ups_action == "TurnOn":
                self.logger.log_message(f"UPS {ups_name} is unhealthy. Output {self.name} will turn ON based on UPSIntegration configuration.", "debug")
                return UPSMode.TURN_ON

        return UPSMode.AUTO

    def are_there_temp_probe_constraints(self, view: SmartDeviceView, new_output_state: bool) -> tuple[bool, bool | None]:  # noqa: ARG002, PLR0912
        """Evaluate the temperature probe constraints to see if they require the output to be off.

        Args:
            view (SmartDeviceView): The current view of the smart devices.
            new_output_state (bool): The proposed new state of the output (True for ON, False for OFF).

        Returns:
            tuple: A tuple containing two booleans. The first boolean is True if a temperature constraint applied, False otherwise.
                   The second boolean indicates the state to override to if a constraint is applied (True for ON, False for OFF). None if no constraint applied.
        """
        current_output_state = view.get_output_state(self.device_output_id)
        for constraint in self.temp_probe_constraints:
            probe_name = constraint.get("TempProbe", "Unknown Probe")
            probe_id = constraint.get("ProbeID")
            condition = constraint.get("Condition")
            set_temp = constraint.get("Temperature")
            fall_back_temp = constraint.get("FallBackTemp")

            if not probe_id or not isinstance(probe_id, int) or not set_temp or not isinstance(set_temp, int | float) or condition not in {"GreaterThan", "LessThan"}:
                continue

            probe_temp = view.get_temp_probe_temperature(probe_id)

            self.logger.log_message(f"Checking constraint: output {self.name}; probe: {probe_name}; condition: {condition}; set temp: {set_temp}°C; fall back temp: {fall_back_temp}°C; probe reads: {probe_temp}", "all")

            if condition == "GreaterThan":
                if probe_temp is None:
                    # Issue 45: If temp probe = N/A for greater than condition, constaint exists
                    self.logger.log_message(f"Output {self.name} cannot turn on because temperature probe {probe_name} reading is not available.", "all")
                    return True, False
                if probe_temp >= set_temp:
                    continue  # No constaint for this condition
                if fall_back_temp is None:  # No fall back range set for this condition
                    if probe_temp < set_temp:
                        self.logger.log_message(f"Output {self.name} cannot turn on because temperature probe {probe_name} is reading {probe_temp:.1f}°C less than a minimum temperature of {set_temp}°C.", "all")
                        return True, False  # Less than set temp and fall back doesn't apply, must stay off
                else:   # Fall back range has been set
                    fall_back_temp = float(fall_back_temp)
                    if probe_temp >= fall_back_temp and probe_temp < set_temp:  # pyright: ignore[reportOperatorIssue]
                        if current_output_state:   # In the range and output currently on
                            self.logger.log_message(f"Output {self.name} is ON and temperature probe {probe_name} is reading {probe_temp:.1f}°C which is within range of {fall_back_temp}°C to {set_temp}°C. No constraint.", "all")
                            continue  # No constaint for this condition
                        else:   # In the range and output currently off  # noqa: RET507
                            self.logger.log_message(f"Output {self.name} is OFF and temperature probe {probe_name} is reading {probe_temp:.1f}°C which is within range of {fall_back_temp}°C to {set_temp}°C. Output must remain off.", "all")
                            return True, False  # Less than set temp and fall back doesn't apply, must stay off
                    if probe_temp < fall_back_temp:
                        self.logger.log_message(f"Output {self.name} cannot turn on because temperature probe {probe_name} is reading {probe_temp:.1f}°C, less than the minimum temperature of {fall_back_temp}°C.", "all")
                        return True, False  # Less than set temp and fall back doesn't apply, must stay off

            if condition == "LessThan":
                if probe_temp is None:
                    # Issue 45: Ignore temp probe = N/A for less than condition
                    self.logger.log_message(f"Temperature probe {probe_name} not available for output {self.name}.", "all")
                    continue
                if probe_temp <= set_temp:
                    continue  # No constaint for this condition
                if fall_back_temp is None:  # No fall back range set for this condition
                    if probe_temp > set_temp:
                        self.logger.log_message(f"Output {self.name} cannot turn on because temperature probe {probe_name} is reading {probe_temp:.1f}°C more than a minimum temperature of {set_temp}°C.", "all")
                        return True, False  # more than set temp and fall back doesn't apply, must stay off
                else:
                    fall_back_temp = float(fall_back_temp)
                    if probe_temp <= fall_back_temp and probe_temp > set_temp:  # pyright: ignore[reportOperatorIssue]
                        if current_output_state:  # In the range and output currently on
                            self.logger.log_message(f"Output {self.name} is ON and temperature probe {probe_name} is reading {probe_temp:.1f}°C which is within range of {fall_back_temp}°C to {set_temp}°C. No constraint.", "all")
                            continue  # No constaint for this condition
                        else:   # In the range and output currently off  # noqa: RET507
                            self.logger.log_message(f"Output {self.name} is OFF and temperature probe {probe_name} is reading {probe_temp:.1f}°C which is within range of {fall_back_temp}°C to {set_temp}°C. Output must remain off.", "all")
                            return True, False  # Less than set temp and fall back doesn't apply, must stay off
                    if probe_temp > fall_back_temp:
                        self.logger.log_message(f"Output {self.name} cannot turn on because temperature probe {probe_name} is reading {probe_temp:.1f}°C, more than the maximum temperature of {fall_back_temp}°C.", "all")
                        return True, False  # Less than set temp and fall back doesn't apply, must stay off

        return False, None
