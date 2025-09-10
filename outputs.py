"""Manages the system state of a specific output device and associated resources."""
from sc_utility import DateHelper, SCLogger, ShellyControl

from enumerations import (
    AmberChannel,
    AppMode,
    InputMode,
    RunPlanMode,
    RunPlanStatus,
    StateReasonOff,
    StateReasonOn,
    SystemState,
)
from pricing import PricingManager
from scheduler import Scheduler


class OutputManager:
    """Manages the state of a single Shelly output device and associated resources."""
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

        # Define the output attributes that we will initialise later
        self.system_state: SystemState = SystemState.AUTO  # The overall system state, to be updated
        self.app_mode = AppMode.AUTO  # Defines the override from the mobile app.
        self.name = None
        self.device_output_name = None
        self.device_output = None
        self.device_mode = RunPlanMode.SCHEDULE
        self.schedule_name = None
        self.schedule = None
        self.amber_channel = AmberChannel.GENERAL
        self.min_hours = self.target_hours = self.max_hours = 0
        self.max_best_price = self.max_priority_price = 0
        self.dates_off = []
        self.device_meter_name = None
        self.device_meter = None
        self.device_input_name = None
        self.device_input = None
        self.device_input_mode = InputMode.IGNORE
        self.parent_device_output_name = None
        self.parent_device_output = None

        # Run planning
        self.run_plan = None

        # Actual hours - these attributes must only be updated by calculate_running_totals()
        self.actual_hours = 0.0
        self.hours_remaining = 0.0
        self.priority_hours_remaining = 0
        self.run_history = None     # This holds a log of all actual runs

        # The required state of the device
        self.is_on = None
        self.last_changed = None
        self.reason = None

        self.initialize(output_config)

        # TO DO: Read state information from disk.

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
                else:
                    self.system_state = SystemState.AUTO

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
                self.amber_channel = output_config.get("AmberChannel", AmberChannel.GENERAL) or AmberChannel.GENERAL
                if self.amber_channel not in AmberChannel:
                    error_msg = f"Invalid AmberChannel {self.amber_channel} for output {self.name}. Must be one of {', '.join([m.value for m in AmberChannel])}."

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
                self.device_input_mode = output_config.get("DeviceInputMode", InputMode.IGNORE) or InputMode.IGNORE
                if self.device_input_mode not in InputMode:
                    error_msg = f"Invalid DeviceInputMode {self.device_input_mode} for output {self.name}. Must be one of {', '.join([m.value for m in InputMode])}."

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
            self.target_hours = 0.0

        # TO DO: Proper implementation
        # Note: hours_remaining shows how many hours we have left to fill. self.run_plan["PlannedHours"] shows how many hours we actually have in the plan.
        self.actual_hours = 0.0  # TO DO: Get this from the run_history object
        self.hours_remaining = self.target_hours - self.actual_hours  # pyright: ignore[reportOptionalOperand]
        self.hours_remaining = max(0.0, self.hours_remaining)  # pyright: ignore[reportArgumentType]
        self.priority_hours_remaining = min(self.min_hours, self.hours_remaining)  # pyright: ignore[reportArgumentType, reportOptionalOperand]

        self.run_history = []
        # TO DO: Add metering information

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

    def evaluate_conditions(self):  # noqa: PLR0912, PLR0915
        """Evaluate the conditions for this output.

        Note: calculate_running_totals should be called before this method.
        """
        new_output_state = None  # This is the new state. Once it's set, we are blocked from further checks
        new_system_state = None
        reason_on = reason_off = None
        # See if the app has overridden our state
        if self.app_mode == AppMode.ON:
            new_output_state = True
            new_system_state = SystemState.APP_OVERRIDE
            reason_on = StateReasonOn.INPUT_SWITCH_ON
        if self.app_mode == AppMode.OFF:
            new_output_state = False
            new_system_state = SystemState.APP_OVERRIDE
            reason_off = StateReasonOff.INPUT_SWITCH_OFF

        # Otherwise see if the Input switch has overridden our state
        if not new_output_state:
            input_state = self._get_input_state()
            if isinstance(input_state, bool):
                if input_state and self.device_input_mode == InputMode.TURN_ON:
                    new_output_state = True
                    new_system_state = SystemState.INPUT_OVERRIDE
                    reason_on = StateReasonOn.INPUT_SWITCH_ON
                if not input_state and self.device_input_mode == InputMode.TURN_OFF:
                    new_output_state = False
                    new_system_state = SystemState.INPUT_OVERRIDE
                    reason_off = StateReasonOff.INPUT_SWITCH_OFF

        # No overrides set, now see if no run today
        if not new_output_state and self._is_today_excluded():
            new_output_state = False
            new_system_state = SystemState.DATE_OFF
            reason_off = StateReasonOff.DATE_OFF

        # If new_output_state hasn't been set at this point, we're in auto mode
        if not new_output_state:
            new_system_state = SystemState.AUTO
            if not self.run_plan or self.run_plan["Status"] == RunPlanStatus.FAILED:
                # We don't have a run plan, generally an error condition
                new_output_state = False
                reason_off = StateReasonOff.NO_RUN_PLAN
            elif self.run_plan["Status"] == RunPlanStatus.NOTHING:
                # We have a valid run plan but there's nothing left to do today
                new_output_state = False
                reason_off = StateReasonOff.RUN_PLAN_COMPLETE
            elif self.run_plan["Status"] in {RunPlanStatus.PARTIAL, RunPlanStatus.READY}:
                # We have a complete or partially filled run plan
                if self.run_plan["StartNow"]:
                    # Run plan tells us to run now.
                    new_output_state = True
                    reason_on = StateReasonOn.ACTIVE_RUN_PLAN
                else:
                    # Run plan tells us to run later.
                    new_output_state = False
                    reason_off = StateReasonOff.INACTIVE_RUN_PLAN

        # If we get here and we still haven't determined the new output state, there's a problem.
        if not isinstance(new_output_state, bool):
            self.logger.log_fatal_error(f"Unable to determine new output state for {self.name}.")

        # If we're proposing to turn on and the system_state is AUTO, then make sure our parent output allows this
        if new_system_state == SystemState.AUTO and new_output_state and self.parent_device_output and not self.parent_device_output["State"]:
            # The output of the parent device is off, so we have to remain off
            new_output_state = False
            reason_off = StateReasonOff.PARENT_OFF

        if new_output_state and reason_on is None:
            self.logger.log_fatal_error(f"Output {self.name} state evaluates to On but reason_on not set.")
        elif not new_output_state and reason_off is None:
            self.logger.log_fatal_error(f"Output {self.name} state evaluates to Off but reason_off not set.")
        # And finally we're ready to apply our changes
        if new_output_state:
            assert reason_on is not None
            self._turn_on(reason_on)
        else:
            assert reason_off is not None
            self._turn_off(reason_off)

    def _get_input_state(self) -> bool | None:
        """Get the current state of the input device if it exists.

        Returns:
            bool | None: The state of the input device (True for ON, False for OFF), or None if no input device is configured.
        """
        if not self.device_input:
            return None
        return self.device_input.get("State")

    def _turn_on(self, new_system_state: SystemState, reason: StateReasonOn):
        """Turns on the output device."""
        # To DO: Actually change the switch state, or deal with it being offline
        # TO DO: only make a change if the state is changing. Update run history regardless
        self.is_on = True
        self.last_changed = DateHelper.now()
        self.system_state = new_system_state
        self.reason = reason
        print(f"Output {self.name} ON - {reason.value}")
        # TO DO: log this in the run_history

    def _turn_off(self, new_system_state: SystemState, reason: StateReasonOff):
        """Turns off the output device.

        Args:
            reason (StateReasonOff): The reason for turning off the output device.
        """
        # To DO: Actually change the switch state, or deal with it being offline
        self.is_on = False
        self.last_changed = DateHelper.now()
        self.system_state = new_system_state
        self.reason = reason
        print(f"Output {self.name} OFF - {reason.value}")
        # TO DO: log this in the run_history

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
