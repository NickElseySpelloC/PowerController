"""Manages the system state of a specific output device and associated resources."""
import datetime as dt

from sc_utility import DateHelper, SCConfigManager, SCLogger, ShellyControl

from enumerations import (
    AmberChannel,
    AppMode,
    InputMode,
    OutputStatusData,
    RunPlanMode,
    RunPlanStatus,
    RunPlanTargetHours,
    StateReasonOff,
    StateReasonOn,
    SystemState,
)
from pricing import PricingManager
from run_history import RunHistory
from scheduler import Scheduler


class OutputManager:
    """Manages the state of a single Shelly output device and associated resources."""
    def __init__(self, output_config: dict, config: SCConfigManager, logger: SCLogger, scheduler: Scheduler, pricing: PricingManager, shelly_control: ShellyControl, saved_state: dict | None = None):
        """Manages the state of a single Shelly output device.

        Args:
            output_config (dict): The configuration for the output device - the config file's OutputConfiguration list entry.
            config (SCConfigManager): The configuration manager for the system.
            logger (SCLogger): The logger for the system.
            scheduler (Scheduler): The scheduler for managing time-based operations.
            pricing (PricingManager): The pricing manager for handling pricing-related tasks.
            shelly_control (ShellyControl): The Shelly control interface.
            saved_state (dict | None): The previously saved state of the output manager, if any.
        """
        self.output_config = output_config
        self.logger = logger
        self.report_critical_errors_delay = config.get("General", "ReportCriticalErrorsDelay", default=None)
        if isinstance(self.report_critical_errors_delay, (int, float)):
            self.report_critical_errors_delay = round(self.report_critical_errors_delay, 0)
        else:
            self.report_critical_errors_delay = None
        self.scheduler = scheduler
        self.pricing = pricing
        self.shelly_control = shelly_control

        # Define the output attributes that we will initialise later
        self.system_state: SystemState = SystemState.AUTO  # The overall system state, to be updated
        self.app_mode = AppMode.AUTO  # Defines the override from the mobile app.
        self.name = None
        self.device = None
        self.device_output_name = None
        self.device_output = None
        self.device_mode = RunPlanMode.SCHEDULE
        self.schedule_name = None
        self.schedule = None
        self.amber_channel = AmberChannel.GENERAL
        self.max_best_price = self.max_priority_price = 0
        self.device_meter_name = None
        self.device_meter = None
        self.device_input_name = None
        self.device_input = None
        self.device_input_mode = InputMode.IGNORE
        self.parent_output_name = None
        self.parent_output = None

        # Run planning
        self.run_plan = None
        self.min_hours = 0
        self.max_hours = 0
        self.run_plan_target_mode = RunPlanTargetHours.ALL_HOURS if output_config.get("TargetHours") == -1 else RunPlanTargetHours.NORMAL
        self.dates_off = []

        try:
            saved_run_history = None
            if saved_state and "RunHistory" in saved_state:
                saved_run_history = saved_state.get("RunHistory")
            self.run_history = RunHistory(self.logger, output_config, saved_run_history)
        except RuntimeError as e:
            self.logger.log_fatal_error(f"Error initializing RunHistory for output {self.name}: {e}")

        # The required state of the device
        self.is_on = saved_state.get("IsOn") if saved_state else None
        self.last_changed = None
        self.reason = None

        self.initialise(output_config)

        # See if the output's saved state matches the actual device state
        assert self.device_output is not None
        if saved_state and self.device_output.get("State") != self.is_on:
            self.logger.log_message(f"Output {self.name} saved state does not match actual device state. Saved: {'On' if self.is_on else 'Off'}, Actual: {'On' if self.device_output.get('State') else 'Off'}. Output relay may have been changed by another application.", "warning")

    def initialise(self, output_config: dict):  # noqa: PLR0912, PLR0915
        """Initializes the output manager with the given configuration.

        Args:
            output_config (dict): The configuration for the output device.

        Raises:
            RuntimeError: If the configuration is invalid.
        """
        self.output_config = output_config
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
                    else:
                        self.device = self.shelly_control.get_device(self.device_output["DeviceID"])

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

            # Min / Max / Target hours
            self.min_hours = output_config.get("MinHours", -1)
            self.max_hours = output_config.get("MaxHours", -1)
            self.run_plan_target_mode = RunPlanTargetHours.ALL_HOURS if output_config.get("TargetHours") == -1 else RunPlanTargetHours.NORMAL
            if self.run_plan_target_mode == RunPlanTargetHours.NORMAL:
                error_msg = None
                target_hours = self._get_target_hours()
                if (self.min_hours < 0 or
                    self.max_hours < self.min_hours or
                    self.max_hours > 24 or
                    target_hours < self.min_hours or
                    target_hours > self.max_hours
                    ):
                    error_msg = f"Invalid MinHours / MaxHours/TargetHours configuration for output {self.name}."
                # Note: TargetHours is set during calculate_running_totals()
            # Note: If self.mode == RunHistoryMode.ALL_DAY, then min / max / target are ignored

            # DatesOff
            if not error_msg:
                dates_off_list = output_config.get("DatesOff", [])
                if len(dates_off_list) > 0:
                    for date_range in dates_off_list:
                        start_date = date_range.get("StartDate")
                        end_date = date_range.get("EndDate")
                        if not start_date or not end_date:
                            error_msg = f"Invalid date range in DatesOff for output {self.name}."
                        else:
                            self.dates_off.append({"StartDate": start_date, "EndDate": end_date})

            # Prices
            if not error_msg:
                self.max_best_price = output_config.get("MaxBestPrice")
                self.max_priority_price = output_config.get("MaxPriorityPrice")
                if not error_msg and (not self.max_best_price or not self.max_priority_price):
                    error_msg = f"MaxBestPrice and MaxPriorityPrice must be properly set for output {self.name}."

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
                self.parent_output_name = output_config.get("ParentOutput")
                # Note: We can't lookup the actual parent output here as it may not have been created yet.

            # Reinitialise the run_history object
            if not error_msg:
                self.run_history.initialise(output_config)

        except (RuntimeError, KeyError) as e:
            raise RuntimeError from e
        else:
            if error_msg:
                raise RuntimeError(error_msg)
            self.calculate_running_totals()   # Finally calculate all running totals

    def get_save_object(self) -> dict:
        """Returns the representation of this output object that can be saved to disk.

        Returns:
            dict: The representation of the output object.
        """
        output_dict = {
            "Name": self.name,
            "SystemState": self.system_state,
            "IsOn": self.is_on,
            "LastChanged": self.last_changed,
            "Reason": self.reason,
            "AppMode": self.app_mode,
            "DeviceMode": self.device_mode,
            "ParentOutputName": self.parent_output_name,
            "DeviceOutputName": self.device_output_name,
            "DeviceMeterName": self.device_meter_name,
            "DeviceInputName": self.device_input_name,
            "DeviceInputMode": self.device_input_mode,
            "ScheduleName": self.schedule_name,
            "AmberChannel": self.amber_channel,
            "MaxBestPrice": self.max_best_price,
            "MaxPriorityPrice": self.max_priority_price,
            "MinHours": self.min_hours,
            "MaxHours": self.max_hours,
            "TargetHours": self._get_target_hours(),
            "RunPlanTargetMode": self.run_plan_target_mode,
            "DatesOff": self.dates_off,
            "RunPlan": self.run_plan,
            "RunHistory": self.run_history.history,
        }
        return output_dict

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

    def calculate_running_totals(self):
        # Update running totals in run_history object

        data_block = self._get_status_data()
        self.run_history.tick(data_block)

    def generate_run_plan(self) -> bool:
        """Generate / update the run plan for this output.

        Returns:
            bool: True if the run plan was successfully generated or updated, False otherwise.
        """
        self.calculate_running_totals()   # Update all the running totals including actual hours from the run history
        self.run_plan = None
        hourly_energy_used = self.run_history.get_hourly_energy_used()

        # Finally calculate the hours remaining for today
        if self.run_plan_target_mode == RunPlanTargetHours.ALL_HOURS:
            required_hours = -1
            priority_hours = self.min_hours
        else:
            target_hours = self._get_target_hours()  # Should not be None
            assert target_hours is not None
            actual_hours = self.run_history.get_actual_hours()
            prior_shortfall, max_shortfall = self.run_history.get_prior_shortfall()
            if prior_shortfall >= max_shortfall and self.report_critical_errors_delay:
                assert isinstance(self.report_critical_errors_delay, int)
                self.logger.report_notifiable_issue(entity=f"Output {self.name}", issue_type="Reached MaxShortfall", send_delay=self.report_critical_errors_delay * 60, message=f"This output has reached the maximum shortfall of {max_shortfall} hours. Please review the configuration to make sure it's possible to run for sufficient hours each day.")  # pyright: ignore[reportArgumentType]
            hours_remaining = target_hours - actual_hours + prior_shortfall
            required_hours = max(0.0, hours_remaining)
            required_hours = min(self.max_hours, required_hours)
            priority_hours = min(self.min_hours, required_hours)

        # If we're in the Best Price mode, get a best price run plan
        if self.device_mode == RunPlanMode.BEST_PRICE:
            self.run_plan = self.pricing.get_run_plan(required_hours=required_hours, priority_hours=priority_hours, max_price=self.max_best_price, max_priority_price=self.max_priority_price, channel_id=self.amber_channel, hourly_energy_usage=hourly_energy_used)  # pyright: ignore[reportArgumentType]

        # If we're in Schedule mode or we get nothing back from Best Price, generate a Schedule
        if self.device_mode == RunPlanMode.SCHEDULE or not self.run_plan:
            self.run_plan = self.scheduler.get_run_plan(self.schedule_name, required_hours=required_hours, priority_hours=priority_hours, max_price=self.max_best_price, max_priority_price=self.max_priority_price, hourly_energy_usage=hourly_energy_used)  # pyright: ignore[reportArgumentType]

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

        # If we get here and we still haven't determined the new system state, there's a problem.
        if not isinstance(new_system_state, SystemState):
            self.logger.log_fatal_error(f"Unable to determine new system state for {self.name}.")
            return
        assert isinstance(new_system_state, SystemState)
        # If we get here and we still haven't determined the new output state, there's a problem.
        if not isinstance(new_output_state, bool):
            self.logger.log_fatal_error(f"Unable to determine new output state for {self.name}.")
            return
        assert isinstance(new_output_state, bool)

        # If we're proposing to turn on and the system_state is AUTO, then make sure our parent output allows this
        if new_system_state == SystemState.AUTO and new_output_state and self.parent_output and not self.parent_output.is_on:
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
            self._turn_on(new_system_state, reason_on)
        else:
            assert reason_off is not None
            self._turn_off(new_system_state, reason_off)

    def _get_input_state(self) -> bool | None:
        """Get the current state of the input device if it exists.

        Returns:
            bool | None: The state of the input device (True for ON, False for OFF), or None if no input device is configured.
        """
        if not self.device_input:
            return None
        return self.device_input.get("State")

    def _get_target_hours(self, for_date: dt.date | None = None) -> float | None:
        """Returns the target hours for the given date.

        Args:
            for_date (dt.date | None): The date for which to retrieve the target hours. Defaults to today.

        Returns:
            float: The target hours for the given date. None if we are in ALL_DAY mode.
        """
        if self.run_plan_target_mode == RunPlanTargetHours.ALL_HOURS:
            return None
        if not for_date:
            for_date = DateHelper.today()

        month = for_date.strftime("%B")

        monthly_target_hours = self.output_config.get("MonthlyTargetHours")
        if monthly_target_hours is not None and month in monthly_target_hours:
            target_hours = monthly_target_hours.get(month)
        else:
            target_hours = self.output_config.get("TargetHours", 8.0)

        # Make sure we haven't exceeded our max hours
        target_hours = min(target_hours, self.max_hours)

        return target_hours

    def _get_current_price(self) -> float:
        """Get the current price from either PricingManager or ScheduleManager depending on the context.

        Returns:
            float: The current price.
        """
        # TO DO: Use PricingManager.get_current_price(self.amber_channel) or ScheduleManager.get_current_price()
        if self.device_mode == RunPlanMode.BEST_PRICE:
            price = self.pricing.get_current_price(self.amber_channel)

        if self.device_mode == RunPlanMode.SCHEDULE or not price:
            # Scheduler will always return a price
            price = self.scheduler.get_current_price(self.schedule)  # pyright: ignore[reportArgumentType]
        return price

    def _get_status_data(self) -> OutputStatusData:
        """Get the status data needed by RunHistory.

        Returns:
            data_block(OutputStatusData)
        """
        return OutputStatusData(
            meter_reading=(self.device_meter.get("Energy") or 0) if self.device_meter else 0,
            target_hours=self._get_target_hours(),
            current_price=self._get_current_price()
        )

    def set_parent_output(self, parent_output):
        """Sets the parent output for this output manager.

        Args:
            parent_output (OutputManager): The parent output manager.
        """
        if not parent_output:
            self.parent_output = None
            return

        # First make sure we're not setting ourselves as our own parent
        if parent_output.name == self.name:
            self.logger.log_fatal_error(f"Output {self.name} cannot be its own parent.")
            return

        # Log warnings if the threshold values don't make sense
        if self.min_hours > parent_output.min_hours:
            self.logger.log_message(f"Output {self.name} has MinHours greater than its parent output {parent_output.name}.", "warning")
        if self.max_hours > parent_output.max_hours:
            self.logger.log_message(f"Output {self.name} has MaxHours greater than its parent output {parent_output.name}.", "warning")

        self.parent_output = parent_output

    def _turn_on(self, new_system_state: SystemState, reason: StateReasonOn):
        """Turns on the output device.

        Args:
            new_system_state (SystemState): The new system state to set.
            reason (StateReasonOn): The reason for turning on the output device.
        """
        assert self.device_output is not None
        assert self.device is not None

        # If actual output is off, we need to turn it on.
        if not self.device_output.get("State"):
            if self.device["Online"]:
                try:
                    self.shelly_control.change_output(self.device_output, True)
                except TimeoutError:
                    self.logger.log_message(f"Device {self.device['Name']} is not responding, cannot turn on output {self.device_output_name}.", "warning")
                except RuntimeError as e:
                    self.logger.log_message(f"Error turning on output {self.device_output_name}: {e}", "error")
            else:
                self.logger.log_message(f"Device {self.device['Name']} is offline, cannot turn on output {self.device_output_name}.", "warning")
                if self.report_critical_errors_delay:
                    assert isinstance(self.report_critical_errors_delay, int)
                    self.logger.report_notifiable_issue(entity=f"Device {self.device['Name']}", issue_type="Device Offline", send_delay=self.report_critical_errors_delay * 60, message=f"Device is offline when trying to turn output {self.device_output_name} on.")  # pyright: ignore[reportArgumentType]

        self.is_on = True

        # If the system_state or reason has changed, update them and log the change
        if self.system_state != new_system_state or self.reason != reason:
            self.system_state = new_system_state
            self.reason = reason
            self.last_changed = DateHelper.now()
            data_block = self._get_status_data()
            self.run_history.start_run(new_system_state, reason, data_block)

        # TO DO: Remove debug
        print(f"Output {self.name} ON - {reason.value}.")
        current_run = self.run_history.get_current_run()
        if current_run:
            print(f"   - Run started at {current_run['StartTime'].strftime('%H:%M:%S')} EnergyUsed: {current_run['EnergyUsed']:.2f}Wh AveragePrice: ${current_run['AveragePrice']:.2f}c/kWh TotalCost: ${current_run['TotalCost']:.4f}")

    def _turn_off(self, new_system_state: SystemState, reason: StateReasonOff):
        """Turns off the output device.

        Args:
            new_system_state (SystemState): The new system state to set.
            reason (StateReasonOff): The reason for turning off the output device.
        """
        assert self.device_output is not None
        assert self.device is not None

        # If actual output is off, we need to turn it on.
        if self.device_output.get("State"):
            if self.device["Online"]:
                try:
                    self.shelly_control.change_output(self.device_output, False)
                except TimeoutError:
                    self.logger.log_message(f"Device {self.device['Name']} is not responding, cannot turn off output {self.device_output_name}.", "warning")
                except RuntimeError as e:
                    self.logger.log_message(f"Error turning off output {self.device_output_name}: {e}", "error")
            else:
                self.logger.log_message(f"Device {self.device['Name']} is offline, cannot turn off output {self.device_output_name}.", "warning")
                if self.report_critical_errors_delay:
                    assert isinstance(self.report_critical_errors_delay, int)
                    self.logger.report_notifiable_issue(entity=f"Device {self.device['Name']}", issue_type="Device Offline", send_delay=self.report_critical_errors_delay * 60, message=f"Device is offline when trying to turn output {self.device_output_name} off.")  # pyright: ignore[reportArgumentType]

        self.is_on = False

        self.system_state = new_system_state
        self.reason = reason
        self.last_changed = DateHelper.now()
        data_block = self._get_status_data()
        self.run_history.stop_run(reason, data_block)

        # TO DO: Remove debug
        print(f"Output {self.name} OFF - {reason.value}")

    def shutdown(self):
        """Shutdown the output manager, turning off the output if it is on."""
        if self.output_config.get("StopOnExit", False) and self.is_on:
            self._turn_off(SystemState.AUTO, StateReasonOff.SHUTDOWN)

    def print_info(self) -> str:
        """Print the information of the output.

        Returns:
            str: The formatted output information.
        """
        # TO DO: Update this function with new attributes
        return_str = f"{self.name} Output Information:\n"
        return_str += f"   - DeviceOutput: {self.device_output_name}\n"
        return_str += f"   - Mode: {self.device_mode}\n"
        return_str += f"   - Schedule: {self.schedule_name}\n"
        return_str += f"   - Amber Channel: {self.amber_channel}\n"
        # return_str += f"   - Min Hours: {self.min_hours}, Max Hours: {self.max_hours}, Target Hours: {self.target_hours}\n"
        # return_str += f"   - Max Best Price: {self.max_best_price}, Max Priority Price: {self.max_priority_price}\n"
        # if self.dates_off:
        #     return_str += "   - Dates Off:\n"
        #     for date_range in self.dates_off:
        #         return_str += f"      - From {date_range.get('StartDate')} to {date_range.get('EndDate')}\n"
        return_str += f"   - Device Meter: {self.device_meter_name}\n"
        return_str += f"   - Device Input: {self.device_input_name} (mode: {self.device_input_mode})\n"
        # return_str += f"   - Parent Device Output: {self.parent_device_output_name}\n"

        return return_str
