"""Manages the system state of a specific output device and associated resources."""
import datetime as dt
import threading
import urllib.parse

from org_enums import (
    AppMode,
    RunPlanMode,
    RunPlanStatus,
    RunPlanTargetHours,
    StateReasonOff,
    StateReasonOn,
    SystemState,
)
from sc_utility import DateHelper, SCConfigManager, SCLogger, ShellyControl

from local_enumerations import (
    FAILED_RUNPLAN_CHECK_INTERVAL,
    RUNPLAN_CHECK_INTERVAL,
    AmberChannel,
    InputMode,
    OutputStatusData,
)
from pricing import PricingManager
from run_history import RunHistory
from run_plan import RunPlanner
from scheduler import Scheduler


class OutputManager:
    """Manages the state of a single Shelly output device and associated resources."""
    def __init__(self, output_config: dict, config: SCConfigManager, logger: SCLogger, scheduler: Scheduler, pricing: PricingManager, shelly_control: ShellyControl, saved_state: dict | None = None):  # noqa: PLR0915
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
        self.config = config
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
        self.id = None  # Lower case, url-safe version of the name
        self.output_config = output_config
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
        self.device_meter_id = None     # TO DO: Remove this eventually
        self.device_input_name = None
        self.device_input = None
        self.device_input_mode = InputMode.IGNORE
        self.parent_output_name = None
        self.parent_output = None
        self.is_parent = False

        # Run planning
        self.run_plan = None
        self.invalidate_run_plan = True
        self.next_run_plan_check = DateHelper.now()
        self.last_price = 0
        self.min_hours = 0
        self.max_hours = 0
        self.run_plan_target_mode = RunPlanTargetHours.ALL_HOURS if output_config.get("TargetHours") == -1 else RunPlanTargetHours.NORMAL
        self.dates_off = []

        # Minimum runtime configuration
        self.min_on_time = 0  # minutes
        self.min_off_time = 0  # minutes

        # Track state change times
        self.last_turned_on = saved_state.get("LastTurnedOn") if saved_state else None
        self.last_turned_off = saved_state.get("LastTurnedOff") if saved_state else None

        try:
            saved_run_history = None
            if saved_state and "RunHistory" in saved_state:
                saved_run_history = saved_state.get("RunHistory")
            self.run_history = RunHistory(self.logger, output_config, saved_run_history)
        except RuntimeError as e:
            self.logger.log_fatal_error(f"Error initializing RunHistory for output {self.name}: {e}")

        # The required state of the device
        self.is_on = saved_state.get("IsOn") if saved_state else None
        self.is_device_online = False  # If device is offline, assume the output is off
        self.last_changed = None
        self.reason = None

        self.initialise(output_config)
        self.logger.log_message(f"Output {self.name} initialised.", "debug")

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
        self.invalidate_run_plan = True  # Force a regeneration of the run plan if config changes
        error_msg = None
        try:
            # Name
            self.name = output_config.get("Name")
            if not self.name:
                error_msg = "Name is not set for an Output configuration."
            else:
                # self.id is url encoded version of name
                self.id = urllib.parse.quote(self.name.lower().replace(" ", "_"))

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

            # Minimum runtime configuration
            self.min_on_time = output_config.get("MinOnTime", 0)  # minutes
            self.min_off_time = output_config.get("MinOffTime", 0)  # minutes
            if self.min_off_time > self.min_on_time:
                error_msg = f"MinOffTime {self.min_off_time} must be less than or equal to MinOnTime {self.min_on_time} for output {self.name}."

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
            "LastTurnedOn": self.last_turned_on,
            "LastTurnedOff": self.last_turned_off,
            "MinOnTime": self.min_on_time,
            "MinOffTime": self.min_off_time,
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

    def tell_device_status_updated(self):
        """Notify this output that the device status may have changed."""
        if not self.device:
            return
        new_online_status = self.device.get("Online")
        if new_online_status != self.is_device_online:
            self.invalidate_run_plan = True
            if new_online_status:
                self.logger.log_message(f"Device {self.device.get('ClientName')} for output {self.name} is now online.", "debug")
                self.logger.clear_notifiable_issue(entity=f"Device {self.device['Name']}", issue_type="Device Offline")
            elif not self.device.get("ExpectOffline", False):
                self.logger.log_message(f"Device {self.device['Name']} is offline.", "warning")
                if self.report_critical_errors_delay:
                    assert isinstance(self.report_critical_errors_delay, int)
                    self.logger.report_notifiable_issue(entity=f"Device {self.device['Name']}", issue_type="Device Offline", send_delay=self.report_critical_errors_delay * 60, message=f"Device is offline when trying to turn output {self.device_output_name} on.")  # pyright: ignore[reportArgumentType]

        self.is_device_online = new_online_status

    def calculate_running_totals(self):
        """Update running totals in run_history object."""
        data_block = self._get_status_data()

        if self.run_history.tick(data_block):
            self.invalidate_run_plan = True  # If we've rolled over to a new day, we need a new run plan

        # Update the remaining hours in the current run plan if we have one
        if self.run_plan:
            RunPlanner.tick(self.run_plan)  # Update the run plan's internal state

    def review_run_plan(self) -> bool:
        """Generate / update the run plan for this output if needed.

        Returns:
            bool: True if the run plan was successfully generated or updated, False otherwise.
        """
        if not self._new_runplan_needed():
            return False

        self.logger.log_message(f"Generating new run plan for output {self.name}", "debug")
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
            if self.report_critical_errors_delay:
                if prior_shortfall >= max_shortfall > 0:
                    assert isinstance(self.report_critical_errors_delay, int)
                    self.logger.report_notifiable_issue(entity=f"Output {self.name}", issue_type="Reached MaxShortfall", send_delay=self.report_critical_errors_delay * 60, message=f"This output has reached the maximum shortfall of {max_shortfall} hours. Please review the configuration to make sure it's possible to run for sufficient hours each day.")  # pyright: ignore[reportArgumentType]
                else:
                    self.logger.clear_notifiable_issue(entity=f"Output {self.name}", issue_type="Reached MaxShortfall")

            hours_remaining = target_hours - actual_hours + prior_shortfall
            required_hours = max(0.0, hours_remaining)
            required_hours = min(self.max_hours, required_hours)
            priority_hours = min(self.min_hours - actual_hours, required_hours)
            priority_hours = max(0.0, priority_hours)

        # If we're in the Best Price mode, get a best price run plan
        if self.device_mode == RunPlanMode.BEST_PRICE:
            self.run_plan = self.pricing.get_run_plan(required_hours=required_hours, priority_hours=priority_hours, max_price=self.max_best_price, max_priority_price=self.max_priority_price, channel_id=self.amber_channel, hourly_energy_usage=hourly_energy_used)  # pyright: ignore[reportArgumentType]

        # If we're in Schedule mode or we get nothing back from Best Price, generate a Schedule
        if self.device_mode == RunPlanMode.SCHEDULE or not self.run_plan:
            self.run_plan = self.scheduler.get_run_plan(self.schedule_name, required_hours=required_hours, priority_hours=priority_hours, max_price=self.max_best_price, max_priority_price=self.max_priority_price, hourly_energy_usage=hourly_energy_used)  # pyright: ignore[reportArgumentType]

        # Log errors and warnings
        if not self.run_plan or self.run_plan["Status"] == RunPlanStatus.FAILED:
            self.next_run_plan_check = DateHelper.now() + dt.timedelta(minutes=FAILED_RUNPLAN_CHECK_INTERVAL)
            logging_level = "warning" if self.run_plan_target_mode == RunPlanTargetHours.ALL_HOURS else "error"
            self.logger.log_message(f"Failed to generate run plan for output {self.name}. Next check at {self.next_run_plan_check.strftime('%H:%M')}.", logging_level)

        elif self.run_plan["Status"] == RunPlanStatus.PARTIAL and self.run_plan_target_mode == RunPlanTargetHours.NORMAL:
            self.next_run_plan_check = DateHelper.now() + dt.timedelta(minutes=FAILED_RUNPLAN_CHECK_INTERVAL)
            self.logger.log_message(f"Partially generated run plan for output {self.name}. Not enough low-price slots to meet target hours. Next check at {self.next_run_plan_check.strftime('%H:%M')}.", "warning")

        else:
            self.next_run_plan_check = DateHelper.now() + dt.timedelta(minutes=RUNPLAN_CHECK_INTERVAL)
            self.logger.log_message(f"Successfully generated run plan for output {self.name}. Next check at {self.next_run_plan_check.strftime('%H:%M')}.", "debug")

        self.invalidate_run_plan = False
        return bool(self.run_plan)

    def _new_runplan_needed(self) -> bool:
        """See if we need to regenerate the run plan.

        Returns:
            bool: True if we need a new run plan, False otherwise.
        """
        # If the device is currently offline, we can't generate a run plan
        if not self.is_device_online:
            return False

        # If some other task has already invalidated the run plan, we need to regenerate it.
        # Also if we don't have a run plan at all
        if self.invalidate_run_plan or not self.run_plan:
            return True

        # If we have a plan but it's complete and there's nothing left to do, we don't need a new plan
        if self.run_plan["Status"] == RunPlanStatus.NOTHING:
            return False

        # See if we're running in a current slot
        current_slot, running_now = RunPlanner.get_current_slot(self.run_plan)

        # If we we're currently in an active run plan slot and the current price has risen significantly, we need a new plan
        if running_now and self.device_mode == RunPlanMode.BEST_PRICE:
            current_price = self.pricing.get_current_price(self.amber_channel)
            if not self.last_price or current_price > self.last_price * 1.1:    # Price has risen by 10% or more
                self.last_price = current_price
                return True

        # Output is on but the run plan is inactive, so we've just gone out of a run plan slot
        if not current_slot and self.is_on and self.system_state == SystemState.AUTO:
            return True

        # Check if it's been a while since we last checked the run plan
        if DateHelper.now() >= self.next_run_plan_check:  # noqa: SIM103
            return True

        return False

    def evaluate_conditions(self):  # noqa: PLR0912, PLR0915
        """Evaluate the conditions for this output.

        Note: calculate_running_totals should be called before this method.
        """
        new_output_state = None  # This is the new state. Once it's set, we are blocked from further checks
        new_system_state = None
        reason_on = reason_off = None
        # See if the app has overridden our state. Only allow changes if the device is online
        if self.is_device_online:
            if self.app_mode == AppMode.ON:
                new_output_state = True
                new_system_state = SystemState.APP_OVERRIDE
                reason_on = StateReasonOn.APP_MODE_ON
            if self.app_mode == AppMode.OFF:
                new_output_state = False
                new_system_state = SystemState.APP_OVERRIDE
                reason_off = StateReasonOff.APP_MODE_OFF

        # Otherwise see if the Input switch has overridden our state. Only allow changes if the device is online
        if new_output_state is None and self.is_device_online:
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
        if new_output_state is None and self._is_today_excluded():
            new_output_state = False
            new_system_state = SystemState.DATE_OFF
            reason_off = StateReasonOff.DATE_OFF

        # If new_output_state hasn't been set at this point, we're in auto mode
        if new_output_state is None:
            new_system_state = SystemState.AUTO
            if not self.is_device_online:
                # Device is offline, so we have to remain off
                new_output_state = False
                reason_off = StateReasonOff.DEVICE_OFFLINE
            elif not self.run_plan or self.run_plan["Status"] == RunPlanStatus.FAILED:
                # We don't have a run plan, generally an error condition
                new_output_state = False
                reason_off = StateReasonOff.NO_RUN_PLAN
            elif self.run_plan["Status"] == RunPlanStatus.NOTHING:
                # We have a valid run plan but there's nothing left to do today
                new_output_state = False
                reason_off = StateReasonOff.RUN_PLAN_COMPLETE
            elif self.run_plan["Status"] in {RunPlanStatus.PARTIAL, RunPlanStatus.READY}:
                # We have a complete or partially filled run plan
                _, run_now = RunPlanner.get_current_slot(self.run_plan)
                if run_now:
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

        if new_output_state and reason_on is None:
            self.logger.log_fatal_error(f"Output {self.name} state evaluates to On but reason_on not set.")
        elif not new_output_state and reason_off is None:
            self.logger.log_fatal_error(f"Output {self.name} state evaluates to Off but reason_off not set.")

        # If we're proposing to turn on and the system_state is AUTO, then make sure our parent output allows this
        if new_system_state == SystemState.AUTO and new_output_state and self.parent_output and not self.parent_output.is_on:
            # The output of the parent device is off, so we have to remain off
            new_output_state = False
            reason_off = StateReasonOff.PARENT_OFF

        # Check minimum runtime constraints before applying changes
        if new_system_state == SystemState.AUTO and self._should_respect_minimum_runtime(new_output_state):
            # message here
            if self.is_on:
                self.reason = StateReasonOn.MIN_ON_TIME
                self.print_to_console(f"Output {self.name} has been ON for less than MinOnTime of {self.min_on_time} minutes. Will remain ON until minimum time has elapsed.")
            else:
                self.reason = StateReasonOff.MIN_OFF_TIME
                self.print_to_console(f"Output {self.name} has been OFF for less than MinOffTime of {self.min_off_time} minutes. Will remain OFF until minimum time has elapsed.")
        else:  # noqa: PLR5501
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
        if not self.is_device_online:
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
        price = None
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
        status_data = OutputStatusData(
            meter_reading=(self.device_meter.get("Energy") or 0) if self.device_meter else 0,
            power_draw=(self.device_meter.get("Power") or 0) if self.device_meter else 0,
            is_on=self.device_output.get("State") or False,  # pyright: ignore[reportOptionalMemberAccess]
            target_hours=self._get_target_hours(),
            current_price=self._get_current_price()
        )

        device_meter_id = hex(id(self.device_meter))

        if not self.device_meter_id:
            self.device_meter_id = device_meter_id
        elif self.device_meter_id != device_meter_id:
            self.logger.log_message(f"Output {self.name} DeviceMeter object has changed from {self.device_meter_id} to {device_meter_id}.", "error")
            self.device_meter_id = device_meter_id

        return status_data

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

    def set_app_mode(self, new_mode: AppMode):
        """Sets the app mode for this output manager.

        Args:
            new_mode (AppMode): The new app mode.
        """
        if new_mode not in AppMode:
            self.logger.log_message(f"Invalid AppMode {new_mode} for output {self.name}.", "error")
            return

        if not self.is_device_online:
            self.logger.log_message(f"Cannot set AppMode to {new_mode.value} for output {self.name} because the device is offline.", "warning")
            return

        if new_mode != self.app_mode:
            self.app_mode = new_mode
            self.logger.log_message(f"Output {self.name} app mode changed to {self.app_mode.value}.", "debug")
            # If the app mode has changed, we need to re-evaluate our state
            self.evaluate_conditions()

    def _turn_on(self, new_system_state: SystemState, reason: StateReasonOn):
        """Turns on the output device.

        Args:
            new_system_state (SystemState): The new system state to set.
            reason (StateReasonOn): The reason for turning on the output device.
        """
        assert self.device_output is not None
        assert self.device is not None

        if not self.is_device_online:
            self.logger.log_message(f"Device {self.device['Name']} is offline, cannot turn on output {self.device_output_name} _turn_on() should not have been called.", "warning")

        # If actual output is off, we need to turn it on.
        if not self.device_output.get("State"):
            try:
                self.shelly_control.change_output(self.device_output, True)
            except TimeoutError:
                self.logger.log_message(f"Device {self.device['Name']} is not responding, cannot turn on output {self.device_output_name}.", "warning")
            except RuntimeError as e:
                self.logger.log_message(f"Error turning on output {self.device_output_name}: {e}", "error")

        # Track when we turned on (only if actually changing state)
        if not self.is_on:  # Only update if we're actually changing from off to on
            self.last_turned_on = DateHelper.now()

        self.is_on = True

        # If the system_state or reason has changed, update them and log the change
        if self.system_state != new_system_state or self.reason != reason:
            self.system_state = new_system_state
            self.reason = reason
            self.last_changed = DateHelper.now()
            data_block = self._get_status_data()
            self.logger.log_message(f"Output {self.name} state changed to ON - {reason.value}.", "detailed")
            self.run_history.start_run(new_system_state, reason, data_block)

        current_run = self.run_history.get_current_run()
        if current_run:
            self.print_to_console(f"Output {self.name} ON - {reason.value}. Started at {current_run['StartTime'].strftime('%H:%M:%S')} Energy Used: {current_run['EnergyUsed']:.2f}Wh Average Price: ${current_run['AveragePrice']:.2f}c/kWh Total Cost: ${current_run['TotalCost']:.4f}")

    def _turn_off(self, new_system_state: SystemState, reason: StateReasonOff):
        """Turns off the output device.

        Args:
            new_system_state (SystemState): The new system state to set.
            reason (StateReasonOff): The reason for turning off the output device.
        """
        assert self.device_output is not None
        assert self.device is not None

        # If actual output is off, we need to turn it on.
        if self.device_output.get("State") and self.is_device_online:
            try:
                self.shelly_control.change_output(self.device_output, False)
            except TimeoutError:
                self.logger.log_message(f"Device {self.device['Name']} is not responding, cannot turn off output {self.device_output_name}.", "warning")
            except RuntimeError as e:
                self.logger.log_message(f"Error turning off output {self.device_output_name}: {e}", "error")

        # Track when we turned off (only if actually changing state)
        if self.is_on:  # Only update if we're actually changing from on to off
            self.last_turned_off = DateHelper.now()

        if self.is_on:
            self.logger.log_message(f"Output {self.name} state changed to OFF - {reason.value}.", "detailed")
        self.is_on = False

        self.system_state = new_system_state
        self.reason = reason
        self.last_changed = DateHelper.now()
        data_block = self._get_status_data()
        self.run_history.stop_run(reason, data_block)

        self.print_to_console(f"Output {self.name} OFF - {reason.value}")

    def shutdown(self):
        """Shutdown the output manager, turning off the output if it is on."""
        if self.output_config.get("StopOnExit", False) and self.is_on:
            self._turn_off(SystemState.AUTO, StateReasonOff.SHUTDOWN)

    def get_info(self) -> str:
        """Print the information of the output.

        Returns:
            str: The formatted output information.
        """
        current_day = self.run_history.get_current_day()
        return_str = f"{self.name} Output Information:\n"
        return_str += f"   - System State: {self.system_state}, reason: {self.reason} (since {self.last_changed.strftime('%H:%M:%S') if self.last_changed else 'N/A'})\n"
        return_str += f"   - Device Output: {self.device_output_name}, currently {'ON' if self.is_on else 'OFF'}\n"
        return_str += f"   - Device Scheduling Mode: {self.device_mode}\n"
        return_str += f"   - Schedule: {self.schedule_name}\n"
        return_str += f"   - Amber Channel: {self.amber_channel}\n"
        return_str += f"   - Min Hours: {self.min_hours}, Max Hours: {self.max_hours}, Target Hours: {self._get_target_hours()}\n"
        return_str += f"   - Max Best Price: {self.max_best_price}c/kWh, Max Priority Price: {self.max_priority_price}c/kWh\n"
        return_str += f"   - Actual hours today: {self.run_history.get_actual_hours():.2f}\n"
        if self.run_plan:
            return_str += f"   - Today's run plan requires {self.run_plan.get('RequiredHours', 0):.2f} hours:\n"
            for entry in self.run_plan.get("RunPlan", []):
                return_str += f"      - From {entry['StartTime'].strftime('%H:%M')} to {entry['EndTime'].strftime('%H:%M')}. Price: {entry['Price']:.2f}c/kWh), Cost: ${entry['EstimatedCost']:.2f}\n"
            return_str += f"      - Planned Hours: {self.run_plan.get('PlannedHours', 0):.2f}, Estimated Cost: ${self.run_plan.get('EstimatedCost', 0):.2f}\n"
        if self.dates_off:
            return_str += "   - Dates off:\n"
            for date_range in self.dates_off:
                return_str += f"      - From {date_range.get('StartDate')} to {date_range.get('EndDate')}\n"
        return_str += f"   - Device Meter: {self.device_meter_name}, Energy Used today: {current_day['EnergyUsed'] if current_day else 0:.2f} kWh\n"
        return_str += f"   - Device Input: {self.device_input_name} (mode: {self.device_input_mode})\n"
        return_str += f"   - Parent Output: {self.parent_output_name}\n"

        return return_str

    def get_webapp_data(self) -> dict:  # noqa: PLR0914
        """Get the data for the web application.

        Returns:
            dict: The web application data.
        """
        target_hours = self._get_target_hours()
        current_day = self.run_history.get_current_day()
        actual_cost = current_day["TotalCost"] if current_day else 0
        forecast_cost = self.run_plan.get("EstimatedCost", 0) if self.run_plan else 0
        actual_energy_used = current_day["EnergyUsed"] if current_day else 0
        forecast_energy_used = self.run_plan.get("ForecastEnergyUsage", 0) if self.run_plan else 0
        forecast_price = self.run_plan.get("ForecastAveragePrice", 0) if self.run_plan else 0

        next_start_dt = self.run_plan.get("NextStartDateTime") if self.run_plan else None
        if next_start_dt and not self.is_on:
            next_start = next_start_dt.strftime("%H:%M")
        else:
            next_start = None
        stopping_at_dt = self.run_plan.get("NextStopDateTime") if self.run_plan else None
        if stopping_at_dt and self.is_on:
            stopping_at = stopping_at_dt.strftime("%H:%M")
        else:
            stopping_at = None
        power_draw = self.device_meter.get("Power", 0) if self.device_meter else 0
        data = {
            "id": self.id,
            "name": self.name,
            "is_on": self.is_on,
            "mode": self.app_mode.value,

            # Information on the run history and plan
            "target_hours": f"{target_hours:.1f}" if target_hours is not None else "Rest of Day",
            "actual_hours": f"{self.run_history.get_actual_hours():.1f}",
            "planned_hours": f"{(self.run_plan.get("RequiredHours", 0) if self.run_plan else 0):.1f}",
            "actual_energy_used": f"{actual_energy_used / 1000:.3f}kWh",
            "actual_cost": f"${actual_cost:.2f}",
            "forecast_energy_used": f"{forecast_energy_used / 1000:.3f}kWh",
            "forecast_cost": f"${forecast_cost:.2f}",
            "forecast_price": f"{forecast_price:.2f} c/kWh" if forecast_price > 0 else "N/A",

            # These are calculated below
            "total_energy_used": 0,
            "total_cost": 0,
            "average_price": 0,

            # Information on the current run
            "next_start_time": next_start,
            "stopping_at": stopping_at,
            "reason": self.reason.value if self.reason else "Unknown",
            "power_draw": f"{power_draw:.0f}W" if power_draw else "None",
            "current_price": f"{self._get_current_price():.1f} c/kWh",
        }
        total_cost = actual_cost + forecast_cost
        data["total_cost"] = f"${total_cost:.2f}"
        total_energy_used = actual_energy_used + forecast_energy_used
        data["total_energy_used"] = f"{total_energy_used / 1000:.3f}kWh"
        average_price = RunHistory.calc_price(total_energy_used, total_cost)
        data["average_price"] = f"{average_price:.2f} c/kWh" if average_price > 0 else "N/A"
        return data

    def print_to_console(self, message: str):
        """Print a message to the console if PrintToConsole is enabled.

        Args:
            message (str): The message to print.
        """
        if self.config.get("General", "PrintToConsole", default=False):
            print(message)

        self.logger.log_message(message, "debug")

    def _should_respect_minimum_runtime(self, proposed_state: bool) -> bool:  # noqa: FBT001
        """Check if we should delay state change due to minimum runtime constraints.

        Args:
            proposed_state (bool): The proposed new state of the output (True for ON, False for OFF).

        Returns:
            bool: True if we should delay the state change, False otherwise.
        """
        now = DateHelper.now()

        # If proposing to turn OFF but haven't met minimum ON time
        if (
            not proposed_state
            and self.is_on
            and self.min_on_time > 0
            and self.last_turned_on
            and self.is_device_online
        ):
            time_on = (now - self.last_turned_on).total_seconds() / 60  # minutes
            if time_on < self.min_on_time:
                remaining = self.min_on_time - time_on
                self.logger.log_message(
                    f"Output {self.name} must stay on for {remaining:.1f} more minutes "
                    f"(MinOnTime: {self.min_on_time})", "debug"
                )
                return True

        # If proposing to turn ON but haven't met minimum OFF time
        if (
            proposed_state
            and not self.is_on
            and self.min_off_time > 0
            and self.last_turned_off
            and self.is_device_online
        ):
            time_off = (now - self.last_turned_off).total_seconds() / 60  # minutes
            if time_off < self.min_off_time:
                remaining = self.min_off_time - time_off
                self.logger.log_message(
                    f"Output {self.name} must stay off for {remaining:.1f} more minutes "
                    f"(MinOffTime: {self.min_off_time})", "debug"
                )
                return True

        return False

    def run_self_tests(self):  # noqa: PLR0914
        """Run self tests on the output manager."""
        print(f"\nRunning self tests for output {self.name}...")
        self.run_plan = None
        hourly_energy_used = 1000

        # Mock some values
        max_hours = 20
        min_hours = 2
        target_hours = 3.5
        actual_hours = 0
        prior_shortfall = 0.5
        max_best_price = 32.0
        max_priority_price = 42.0
        min_slot_length = 10  # minutes
        min_time_between_slots = 5  # minutes
        channel = AmberChannel.GENERAL
        schedule = "Hot Water"

        # Calculate the inputs
        hours_remaining = target_hours - actual_hours + prior_shortfall
        required_hours = max(0.0, hours_remaining)
        required_hours = min(max_hours, required_hours)
        priority_hours = min(min_hours, required_hours)

        # Get a best price run plan
        run_plan = self.pricing.get_run_plan(required_hours=required_hours,
                                             priority_hours=priority_hours,
                                             max_price=max_best_price,
                                             max_priority_price=max_priority_price,
                                             channel_id=channel,
                                             hourly_energy_usage=hourly_energy_used,
                                             slot_min_minutes=min_slot_length,
                                             slot_min_gap_minutes=min_time_between_slots)  # pyright: ignore[reportArgument
        if run_plan:
            print(f"Best Price: {RunPlanner.print_info(run_plan, self.name)}")
        else:
            print(f"Self Test Best Price Run Plan: No run plan could be generated for output {self.name}.")

        # # Get a Schedule run plan
        run_plan = self.scheduler.get_run_plan(operating_schedule_name=schedule,
                                               required_hours=required_hours,
                                               priority_hours=priority_hours,
                                               max_price=max_best_price,
                                               max_priority_price=max_priority_price,
                                               hourly_energy_usage=hourly_energy_used,
                                               slot_min_minutes=min_slot_length,
                                               slot_min_gap_minutes=min_time_between_slots)  # pyright: ignore[reportArgumentType]
        if run_plan:
            print(f"Schedule: {RunPlanner.print_info(run_plan, self.name)}")
        else:
            print(f"Self Test Schedule Run Plan: No run plan could be generated for output {self.name}.")

    @staticmethod
    def _get_current_thread_name() -> str:
        """Get the name of the current thread.

        Returns:
            str: The name of the current thread.
        """
        return threading.current_thread().name

    def get_consumption_data(self) -> list[dict]:
        """Get the consumption data for this output.

        Returns:
            list[dict]: The list of consumption data points.
        """
        if self.run_history:
            return self.run_history.get_consumption_data()
        return []
