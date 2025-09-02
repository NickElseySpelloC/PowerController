"""Manages the system state of a specific output device and associated resources."""
from sc_utility import DateHelper, SCLogger, ShellyControl

from enumerations import (
    AppMode,
    RunPlanMode,
    StateReasonOff,
    StateReasonOn,
    SystemState,
)
from pricing import PricingManager
from scheduler import Scheduler


class OutputState:
    def __init__(self):
        self.is_on = False
        self.reason = None
        self.app_mode = AppMode.AUTO  # Defines the override from the mobile app.
        self.last_changed = None

    def turn_on(self, reason: StateReasonOn):
        """Turns on the output device."""
        self.is_on = True
        self.last_changed = DateHelper.now()
        self.reason = reason
        # TO DO: log this in the run_history

    def turn_off(self, reason: StateReasonOff):
        """Turns off the output device.

        Args:
            reason (StateReasonOff): The reason for turning off the output device.
        """
        self.is_on = False
        self.last_changed = DateHelper.now()
        self.reason = reason
        # TO DO: log this in the run_history


class OutputManager:
    def __init__(self, output_config: dict, logger: SCLogger, scheduler: Scheduler, pricing: PricingManager, shelly_control: ShellyControl):
        """Manages the state of a single Shelly output device.

        Args:
            output_config (dict): The configuration for the output device - the config file's OutputConfiguration list entry.
            logger (SCLogger): The logger for the system.
            scheduler (Scheduler): The scheduler for managing time-based operations.
            pricing (PricingManager): The pricing manager for handling pricing-related tasks.
            shelly_control (ShellyControl): The Shelly control interface.
        """
        self.logger = logger
        self.scheduler = scheduler
        self.pricing = pricing
        self.shelly_control = shelly_control

        # Create an instance of the OutputState object
        self.output_state = OutputState()

        # Define the output attributes that we will initialise later
        self.system_state: SystemState = SystemState.SCHEDULED  # The overall system state, to be updated
        self.name = None
        self.device_output_name = None
        self.device_output = None
        self.device_mode = RunPlanMode.SCHEDULE
        self.schedule_name = None
        self.schedule = None
        self.amber_channel = "general"
        self.min_hours = self.target_hours = self.max_hours = 0
        self.max_best_price = self.max_priority_price = 0
        self.dates_off = []
        self.device_meter_name = None
        self.device_meter = None
        self.device_input_name = None
        self.device_input = None
        self.device_input_mode = "Ignore"
        self.parent_device_output_name = None
        self.parent_device_output = None

        # Run planning
        self.run_plan = None

        # Actual hours - these attributes must only be updated by calculate_running_totals()
        self.actual_hours = 0.0
        self.hours_remaining = 0.0
        self.priority_hours_remaining = 0
        self.run_history = None     # This holds a log of all actual runs

        self.initialize(output_config)

    def initialize(self, output_config: dict):  # noqa: PLR0912, PLR0915
        """Initializes the output manager with the given configuration.

        Args:
            output_config (dict): The configuration for the output device.

        Raises:
            RuntimeError: If the configuration is invalid.
        """
        error_msg = None
        try:
            # Name
            self.name = output_config.get("Name")
            if not self.name:
                error_msg = "Name is not set for an Output configuration."

            # DeviceOutput
            if not error_msg:
                self.device_output_name = output_config.get("DeviceOutput")
                if not self.device_output_name:
                    error_msg = f"DeviceOutput is not set for output {self.name}."
                else:
                    self.device_output = self.shelly_control.get_device_component("output", self.device_output_name)
                    if not self.device_output:
                        error_msg = f"DeviceOutput {self.device_output_name} not found for output {self.name}."

            # Mode
            if not error_msg:
                self.device_mode = output_config.get("Mode")
                if not self.device_mode or self.device_mode not in RunPlanMode:
                    error_msg = f"A valid mode has not been set for output {self.name}."
                if self.device_mode == RunPlanMode.BEST_PRICE:
                    self.system_state = SystemState.BEST_PRICE
                else:
                    self.system_state = SystemState.SCHEDULED

            # Schedule
            if not error_msg:
                self.schedule_name = output_config.get("Schedule")
                if self.schedule_name:
                    self.schedule = self.scheduler.get_schedule_by_name(self.schedule_name)
                    if not self.schedule:
                        error_msg = f"Schedule {self.schedule_name} for output {self.name} not found in OperatingSchedules."
                elif self.device_mode == RunPlanMode.SCHEDULE:
                    error_msg = f"Schedule is not set for output {self.name}. This is required if Mode is Schedule."

            # AmberChannel
            if not error_msg:
                self.amber_channel = output_config.get("AmberChannel", "general") or "general"
                if self.amber_channel not in {"general", "controlledLoad"}:
                    error_msg = f"Invalid AmberChannel {self.amber_channel} for output {self.name}. Must be 'general' or 'controlledLoad'."

            # Hours and prices
            if not error_msg:
                self.min_hours = output_config.get("MinHours")
                self.target_hours = output_config.get("TargetHours")
                self.max_hours = output_config.get("MaxHours")
                self.max_best_price = output_config.get("MaxBestPrice")
                self.max_priority_price = output_config.get("MaxPriorityPrice")
                if not self.min_hours or not self.target_hours or not self.max_hours:
                    error_msg = f"MinHours, TargetHours, and MaxHours must be properly set for output {self.name}."
                if not error_msg and (not self.max_best_price or not self.max_priority_price):
                    error_msg = f"MaxBestPrice and MaxPriorityPrice must be properly set for output {self.name}."

            # DatesOff
            if not error_msg:
                dates_off_list = output_config.get("DatesOff", [])
                if len(dates_off_list) > 0:
                    for date_range in dates_off_list:
                        start_date = date_range.get("StartDate")
                        end_date = date_range.get("EndDate")
                        if not start_date or not end_date:
                            error_msg = f"Invalid date range in DatesOff for output {self.name}."
                            break
                        self.dates_off.append({"StartDate": start_date, "EndDate": end_date})

            # DeviceMeter
            if not error_msg:
                self.device_meter_name = output_config.get("DeviceMeter")
                if self.device_meter_name:
                    self.device_meter = self.shelly_control.get_device_component("meter", self.device_meter_name)
                    if not self.device_meter:
                        error_msg = f"DeviceMeter {self.device_meter_name} not found for output {self.name}."

            # DeviceInput
            if not error_msg:
                self.device_input_name = output_config.get("DeviceInput")
                if self.device_input_name:
                    self.device_input = self.shelly_control.get_device_component("input", self.device_input_name)
                    if not self.device_input:
                        error_msg = f"DeviceInput {self.device_input_name} not found for output {self.name}."

            # DeviceInputMode
            if not error_msg:
                self.device_input_mode = output_config.get("DeviceInputMode", "Ignore") or "Ignore"
                if self.device_input_mode not in {"Ignore", "TurnOn", "TurnOff"}:
                    error_msg = f"Invalid DeviceInputMode {self.device_input_mode} for output {self.name}. Must be 'Ignore', 'TurnOn', or 'TurnOff'."

            # ParentDeviceOutput
            if not error_msg:
                self.parent_device_output_name = output_config.get("ParentDeviceOutput")
                if self.parent_device_output_name:
                    self.parent_device_output = self.shelly_control.get_device_component("output", self.parent_device_output_name)
                    if not self.parent_device_output:
                        error_msg = f"ParentDeviceOutput {self.parent_device_output_name} not found for output {self.name}."

        except (RuntimeError, KeyError) as e:
            raise RuntimeError from e
        else:
            if error_msg:
                raise RuntimeError(error_msg)
            self.calculate_running_totals()   # Finally calculate all running totals

    def calculate_running_totals(self):
        """Calculate all the running totals for this object and State object. Update actual_hours, hours_remaining, run_history."""
        # See if we have a DatesOff override for today
        if self._is_today_excluded():
            self.system_state = SystemState.DATE_OFF
            self.target_hours = 0.0

        # TO DO: Proper implementation
        self.actual_hours = 0.0
        self.hours_remaining = self.target_hours - self.actual_hours  # pyright: ignore[reportOptionalOperand]
        self.hours_remaining = max(0.0, self.hours_remaining)  # pyright: ignore[reportArgumentType]
        self.priority_hours_remaining = min(self.min_hours, self.hours_remaining)  # pyright: ignore[reportArgumentType, reportOptionalOperand]

        self.run_history = []
        # TO DO: Add metering information
        pass

    def generate_run_plan(self) -> bool:
        """Generate / update the run plan for this output.

        Returns:
            bool: True if the run plan was successfully generated or updated, False otherwise.
        """
        self.calculate_running_totals()   # Update all the running totals including hours_remaining
        self.run_plan = None

        # If we're in the Best Price mode, get a best price run plan
        if self.device_mode == RunPlanMode.BEST_PRICE:
            self.run_plan = self.pricing.get_run_plan(required_hours=self.hours_remaining, priority_hours=self.priority_hours_remaining, max_price=self.max_best_price, max_priority_price=self.max_priority_price)  # pyright: ignore[reportArgumentType]

        # If we're in Schedule mode or we get nothing back from Best Price, generate a Schedule
        if self.device_mode == RunPlanMode.SCHEDULE or not self.run_plan:
            self.run_plan = self.scheduler.get_run_plan(self.schedule_name, required_hours=self.hours_remaining, priority_hours=self.priority_hours_remaining, max_price=self.max_best_price, max_priority_price=self.max_priority_price)  # pyright: ignore[reportArgumentType]

        return bool(self.run_plan)

    def evaluate_conditions(self):
        """Evaluate the conditions for this output."""
        # TO DO: Implement condition evaluation logic
        print(f"Evaluating conditions for output {self.name}")

    def print_info(self) -> str:
        """Print the information of the output.

        Returns:
            str: The formatted output information.
        """
        return_str = f"{self.name} Output Information:\n"
        return_str += f"   - DeviceOutput: {self.device_output_name}\n"
        return_str += f"   - Mode: {self.device_mode}\n"
        return_str += f"   - Schedule: {self.schedule_name}\n"
        return_str += f"   - Amber Channel: {self.amber_channel}\n"
        return_str += f"   - Min Hours: {self.min_hours}, Max Hours: {self.max_hours}, Target Hours: {self.target_hours}\n"
        return_str += f"   - Max Best Price: {self.max_best_price}, Max Priority Price: {self.max_priority_price}\n"
        if self.dates_off:
            return_str += "   - Dates Off:\n"
            for date_range in self.dates_off:
                return_str += f"      - From {date_range.get('StartDate')} to {date_range.get('EndDate')}\n"
        return_str += f"   - Device Meter: {self.device_meter_name}\n"
        return_str += f"   - Device Input: {self.device_input_name} (mode: {self.device_input_mode})\n"
        return_str += f"   - Parent Device Output: {self.parent_device_output_name}\n"

        return return_str

    def _is_today_excluded(self) -> bool:
        """Check if today falls within any specified DatesOff range which states that the output should be off.

        Returns:
            result(bool): True if today is excluded, False otherwise.
        """
        today = DateHelper.today()
        for rng in self.dates_off:
            if rng["StartDate"] <= today <= rng["EndDate"]:
                return True
        return False
