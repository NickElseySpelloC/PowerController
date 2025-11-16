"""The PowerController class that orchestrates power management."""
import csv
import datetime as dt
import queue

# from threading import Event
import time
from collections.abc import Callable
from pathlib import Path
from threading import Event

from org_enums import AppMode, StateReasonOff, SystemState
from sc_utility import (
    DateHelper,
    JSONEncoder,
    SCCommon,
    SCConfigManager,
    SCLogger,
)

from external_services import ExternalServiceHelper
from local_enumerations import (
    SCHEMA_VERSION,
    Command,
    LookupMode,
    OutputAction,
    OutputActionType,
)
from outputs import OutputManager
from pricing import PricingManager
from scheduler import Scheduler
from shelly_view import ShellyView
from shelly_worker import (
    ShellySequenceRequest,
    ShellySequenceResult,
    ShellyStep,
    ShellyWorker,
    StepKind,
)


class PowerController:
    """The PowerController class that orchestrates power management."""

    # Public Functions ============================================================================
    def __init__(self, config: SCConfigManager, logger: SCLogger, shelly_worker: ShellyWorker, wake_event: Event):
        """Initializes the PowerController.

        Args:
            config (SCConfigManager): The configuration manager for the system.
            logger (SCLogger): The logger for the system.
            shelly_worker: The ShellyWorker obeject that we use to interface to ShellyControl
            wake_event (Event): The event used to wake the controller.
        """
        self.config = config
        self.last_config_check = DateHelper.now()
        self.logger = logger
        self.external_service_helper = ExternalServiceHelper(config, logger)
        self.viewer_website_last_post = None
        self.wake_event = wake_event
        self.shelly_worker: ShellyWorker = shelly_worker
        self.all_shelly_devices_online = None    # This must only be set / queried in _refresh_device_statuses()
        self.cmd_q: queue.Queue[Command] = queue.Queue()    # Used to post commands into the controller's loop
        self.command_pending: bool = False
        self.report_critical_errors_delay = config.get("General", "ReportCriticalErrorsDelay", default=None)
        if isinstance(self.report_critical_errors_delay, (int, float)):
            self.report_critical_errors_delay = round(self.report_critical_errors_delay, 0)
        else:
            self.report_critical_errors_delay = None

        # Setup the environment
        self.outputs = []   # List of output state managers, each one a OutputStateManager object.
        self.poll_interval = 10.0

        # Create the two run_planner types
        self.scheduler = Scheduler(self.config, self.logger)
        self.pricing = PricingManager(self.config, self.logger)

        self._initialise(skip_shelly_initialization=True)

    def get_webapp_data(self) -> dict:
        """Returns a dict object with a snapshot of the current state of all outputs.

        Returns:
            dict: The state snapshot containing theoutputs.
        """
        loop_count = 0
        while self._have_pending_commands() and loop_count < 10:
            time.sleep(0.1)  # Small delay to let the commands be processed
            loop_count += 1

        view = self._get_latest_status_view()

        # Now build the snapshot
        global_data = {
            "access_key": self.config.get("Website", "AccessKey"),
            "AppLabel": self.app_label,
            "PollInterval": self.webapp_refresh,
        }

        outputs_data = {
            output.id: output.get_webapp_data(view)
            for output in self.outputs
        }

        return_dict = {
            "global": global_data,
            "outputs": outputs_data,
        }

        return return_dict

    def is_valid_output_id(self, output_id: str) -> bool:
        """Check if the output ID is valid.

        Args:
            output_id (str): The output ID to check.

        Returns:
            bool: True if the output ID is valid, False otherwise.
        """
        if not isinstance(output_id, str):
            return False

        return any(output.id == output_id for output in self.outputs)

    def post_command(self, cmd: Command) -> None:
        """Post a command to the controller from the web app."""
        self.cmd_q.put(cmd)
        self.command_pending: bool = True
        self.wake_event.set()

    def run(self, stop_event: Event):
        """The main loop of the power controller.

        Args:
            stop_event (Event): The event used to stop the controller.
        """
        self.logger.log_message("Power controller starting main control loop.", "detailed")

        if self.run_self_tests():
            return

        while not stop_event.is_set():
            self.print_to_console(f"Main tick at {DateHelper.now().strftime('%H:%M:%S')}")
            self._clear_commands()          # Get all commands from the queue and apply them
            self._run_scheduler_tick()
            self.wake_event.clear()
            self.wake_event.wait(timeout=self.poll_interval)

        self.shutdown()

    def shutdown(self):
        """Shutdown the power controller, turning off outputs if configured to do so."""
        self.logger.log_message("Interrupt received, shutting down power controller...", "summary")
        view = self._get_latest_status_view()
        for output in self.outputs:
            if output.shutdown(view):
                requested_action = OutputAction(
                    worker_request_id=None,
                    type=OutputActionType.TURN_OFF,
                    system_state=SystemState.AUTO,
                    reason=StateReasonOff.SHUTDOWN)

                self._execute_action_on_output(output, requested_action, view)

        self._save_system_state(force_post=True)

    def print_to_console(self, message: str):
        """Print a message to the console if PrintToConsole is enabled.

        Args:
            message (str): The message to print.
        """
        if self.config.get("General", "PrintToConsole", default=False):
            print(message)

        self.logger.log_message(message, "debug")

    def run_self_tests(self) -> bool:
        """Run self tests on all outputs then exit.

        Returns:
            bool: True if we should exit after the tests, False otherwise.
        """
        if not self.config.get("General", "TestingMode", default=False):
            return False

        for output in self.outputs:
            output.run_self_tests()

        return True

    # Helper to post a long-running sequence (for OutputManager to call)
    def post_shelly_sequence(
        self,
        steps: list[ShellyStep],
        label: str = "",
        timeout_s: float | None = None,
        on_complete: Callable[[ShellySequenceResult], None] | None = None,
    ) -> str | None:
        if not self.shelly_worker:
            self.logger.log_message("Shelly worker not available; cannot run sequence.", "error")
            return None

        # Default callback posts a command back to the controller loop with the result.
        def default_on_complete(res: ShellySequenceResult):
            self.post_command(Command("shelly_sequence_completed", {
                "sequence_id": res.id,
                "label": label,
                "ok": res.ok,
                "error": res.error,
            }))

        req = ShellySequenceRequest(
            steps=steps,
            label=label,
            timeout_s=timeout_s,
            on_complete=on_complete or default_on_complete,
        )
        return self.shelly_worker.submit(req)

    # Example: schedule “turn on O1, wait 60s, turn on O2” and notify via Command when done
    def example_long_running_sequence(self):
        steps = [
            ShellyStep(StepKind.CHANGE_OUTPUT, {"output_identity": "Sydney Dev A O1", "state": True}, retries=2, retry_backoff_s=1.0),
            ShellyStep(StepKind.SLEEP, {"seconds": 60}),
            ShellyStep(StepKind.REFRESH_STATUS, {"output_identity": "Sydney Dev A O2", "state": True}, retries=2, retry_backoff_s=1.0),
        ]
        job_id = self.post_shelly_sequence(steps, label="pool-seq", timeout_s=180)
        self.logger.log_message(f"Submitted pool sequence job_id={job_id}", "debug")

    # Private Functions ===========================================================================
    def _initialise(self, skip_shelly_initialization: bool | None = False):  # noqa: FBT001, FBT002, PLR0912, PLR0915
        """(re) initialise the power controller."""
        # See if we have a system state file to load
        saved_state = self._load_system_state()
        if saved_state:
            self.logger.log_message("Initializing power controller from saved state.", "debug")
        else:
            self.logger.log_message("No saved state found, initializing power controller from scratch.", "debug")

        self.poll_interval = int(self.config.get("General", "PollingInterval", default=30) or 30)  # pyright: ignore[reportArgumentType]
        self.webapp_refresh = int(self.config.get("Website", "PageAutoRefresh", default=10) or 10)  # pyright: ignore[reportArgumentType]
        self.app_label = self.config.get("General", "Label", default="PowerController")

        # Reinitialise if needed
        if not skip_shelly_initialization:
            # Reinitialise the Shelly controller and get the latest status
            self.shelly_worker.reinitialise_settings()
        # Get the latest ShellyStatus view
        view = self._get_latest_status_view()

        # Confirm that the configured output names are unique
        output_names = [o["Name"] for o in self.config.get("Outputs", default=[]) or []]
        if len(output_names) != len(set(output_names)):
            self.logger.log_fatal_error("Output names must be unique.")
            return

        # Loop through each output read from the config file
        # Create an instance of a OutputStateManager manager object for each output we're managing
        outputs_config = self.config.get("Outputs", default=[]) or []
        self.outputs.clear()    # Clear any existing outputs
        try:
            for output_cfg in outputs_config:
                # Search for an existing output with the same name and update it if found
                if any(o.name == output_cfg.get("Name") for o in self.outputs):
                    existing_output = next(o for o in self.outputs if o.name == output_cfg.get("Name"))
                    existing_output.initialise(output_cfg, view)
                    continue

                # See if we can find saved state for this output
                output_state = None
                if saved_state and "Outputs" in saved_state:
                    output_state = next((o for o in saved_state["Outputs"] if o.get("Name") == output_cfg.get("Name")), None)

                # Create a new output manager
                output_manager = OutputManager(output_cfg, self.config, self.logger, self.scheduler, self.pricing, view, output_state)
                self.outputs.append(output_manager)
        except RuntimeError as e:
            self.logger.log_fatal_error(f"Error initializing outputs: {e}")

        # Now remove any outputs that are no longer in the config file
        self.outputs = [o for o in self.outputs if any(o.name == cfg.get("Name") for cfg in outputs_config)]

        # Now link outputs to their parent outputs if needed
        for output in self.outputs:
            if output.parent_output_name:
                parent = next((o for o in self.outputs if o.name == output.parent_output_name), None)
                if parent:
                    output.set_parent_output(parent)

        # Finally do some cross output validation
        for output in self.outputs:
            # Make sure the output's parent is not itself or a child of itself
            if output.parent_output:
                parent = output.parent_output
                parent.is_parent = True
                while parent:
                    if parent == output:
                        self.logger.log_fatal_error(f"Output {output.name} cannot be its own parent or a child of itself.")
                        break
                    parent = parent.parent_output

            # Make sure each output device is only used once
            list_output_devices = self._find_output(LookupMode.OUTPUT, output.device_output_name)
            if len(list_output_devices) > 1:
                self.logger.log_fatal_error(f"Output device {output.device_output_name} is used by more than one output.")

            # Display a warning if mutiple outputs use the same meter device
            list_meter_devices = self._find_output(LookupMode.METER, output.device_meter_name)
            if len(list_meter_devices) > 1:
                self.logger.log_message(f"Meter device {output.device_meter_name} is used by {output.name} and at least one other output.", "warning")

        # Sort outputs so parents are evaluated first
        list.sort(self.outputs, key=lambda x: not x.is_parent)

        # Reinitialize the scheduler and pricing manager
        self.scheduler.initialise()
        self.pricing.initialise()

    def _get_system_state_path(self) -> Path | None:
        """Get the path to the system state file from the configuration.

        Returns:
            Path | None: The path to the system state file, or None if not configured.
        """
        system_state_file = self.config.get("Files", "SavedStateFile")
        if system_state_file:
            return SCCommon.select_file_location(system_state_file)  # pyright: ignore[reportArgumentType]
        return None

    def _load_system_state(self) -> dict | None:
        """Loads the system state from disk.

        Returns:
            dict | None: The loaded system state, or None if not found or error.
        """
        system_state_path = self._get_system_state_path()
        if not system_state_path or not system_state_path.exists():
            return None

        try:
            state_data = JSONEncoder.read_from_file(system_state_path)
            if not state_data:
                return None
            assert isinstance(state_data, dict)
            if state_data.get("StateFileType") != "PowerController":
                self.logger.log_fatal_error(f"Invalid system state file type {state_data.get('StateFileType')}, cannot load file {system_state_path.name}")
                return None

        except RuntimeError as e:
            self.logger.log_fatal_error(f"Error loading system state: {e}")
        else:
            self.logger.log_message(f"Loaded system state from {system_state_path}", "debug")
            return state_data

    def _save_system_state(self, force_post: bool = False):  # noqa: FBT001, FBT002
        """Saves the system state to disk.

        Args:
            force_post (bool): If True, force posting the state to the web viewer.
        """
        # Save the output consumption data if needed
        self._save_output_consumption_data()

        system_state_path = self._get_system_state_path()
        if not system_state_path:
            return

        try:
            save_object = {
                "SchemaVersion": SCHEMA_VERSION,
                "StateFileType": "PowerController",
                "DeviceName": self.app_label,
                "SaveTime": DateHelper.now(),
                "Outputs": [],
                "Scheduler": self.scheduler.get_save_object(),
            }
            for output in self.outputs:
                output_save_object = output.get_save_object()
                save_object["Outputs"].append(output_save_object)

            # Save the file
            JSONEncoder.save_to_file(save_object, system_state_path)
        except (TypeError, ValueError, RuntimeError, OSError) as e:
            self.logger.log_fatal_error(f"Error saving system state: {e}")
        else:
            self.logger.log_message(f"System state saved to {system_state_path}", "debug")

        # Post to the web server if needed - this function takes care of frequency checks
        # Break each output into a seperate post to reduce the size of each post
        frequency = self.config.get("ViewerWebsite", "Frequency", default=30) or 30
        if self.config.get("ViewerWebsite", "Enable", default=False):
            if self.viewer_website_last_post:
                time_since_last_post = (DateHelper.now() - self.viewer_website_last_post).total_seconds()
            else:
                time_since_last_post = frequency + 1   # pyright: ignore[reportOperatorIssue]
            if time_since_last_post >= frequency or force_post:  # pyright: ignore[reportOperatorIssue]
                for output in self.outputs:
                    post_object = {
                        "SchemaVersion": SCHEMA_VERSION,
                        "StateFileType": "PowerController",
                        "DeviceName": f"{self.app_label} - {output.name}",
                        "SaveTime": DateHelper.now(),
                        "Output": output.get_save_object(),
                        "Scheduler": self.scheduler.get_save_object(output.schedule),
                    }
                    self.external_service_helper.post_state_to_web_viewer(post_object)
                self.viewer_website_last_post = DateHelper.now()

    # Private Functions ===========================================================================
    def _run_scheduler_tick(self):
        """Do all the control processing of the main loop."""
        # Refresh the Amber price data if it's time to do so
        self.pricing.refresh_price_data_if_time()

        # Get a snapshot of all Shelly devices
        view = self._refresh_device_statuses()

        # Calculate the running totals for each output
        self._calculate_running_totals(view)

        # Regenerate the run_plan for each output if needed
        self._review_run_plans()

        # Evaluate the conditions for each output and make changes if needed
        self._evaluate_conditions(view)

        # Deal with config changes including downstream objects
        self._check_for_configuration_changes()

        # Save the system state to disk
        self._save_system_state()

        # Ping the heartbeat monitor - this function takes care of frequency checks
        self.external_service_helper.ping_heatbeat()

        # Check for fatal error recovery
        self._check_fatal_error_recovery()

    def _refresh_device_statuses(self) -> ShellyView:
        """Refresh the status of all devices.

        Returns:
            A ShellyView object
        """
        # Post a refresh job and wait for it to complete (bounded wait)
        req_id = self.shelly_worker.request_refresh_status()
        # Make timeout configurable if you like; 3s is a reasonable default
        done = self.shelly_worker.wait_for_result(req_id, timeout=3.0)
        if not done:
            self.logger.log_message("Timed out waiting for Shelly refresh; using last snapshot.", "warning")

        view = self._get_latest_status_view()

        # TO DO: Remove this
        view_snapshot = view.get_json_snapshot()
        # Save the JSON snapshot to a file for debugging
        debug_file_path = SCCommon.select_file_location("debug_shelly_view_snapshot.json")
        if debug_file_path:
            try:
                JSONEncoder.save_to_file(view_snapshot, debug_file_path)
                self.logger.log_message(f"Saved Shelly view snapshot to {debug_file_path}", "debug")
            except (TypeError, ValueError, RuntimeError, OSError) as e:
                self.logger.log_message(f"Failed to save Shelly view snapshot: {e}", "warning")

        # Tell outputs device status updated
        for output in self.outputs:
            output.tell_device_status_updated(view)

        # Now see if we need to reinitialise the Shelly controller because a device that was offline during startup has come back online
        new_online_status = view.all_devices_online()
        if new_online_status and not self.all_shelly_devices_online:
            self.logger.log_message("All Shelly devices are now online, reinitializing...", "detailed")
            self._save_system_state(force_post=True)  # Save state before reinitialising
            self._initialise()

            # Make sure we don't repeat this block again
            self.all_shelly_devices_online = new_online_status

        return view

    def _get_latest_status_view(self) -> ShellyView:
        """Get the latest ShellyView snapshot from the ShellyWorker.

        Returns:
            ShellyView: The latest ShellyView snapshot.
        """
        # Get a deep copy of all the Shelly devices
        snapshot = self.shelly_worker.get_latest_status()

        # TO DO: Deal with the fact that snapshot may be empty / invalid if the refresh failed or devices are offline

        # And create a new ShellyView instance to reference this data
        view = ShellyView(snapshot)

        # TO DO: Remove debug code
        # try:
        #     device_name_pool_solar = "Sydney Pool Solar"
        #     print(f"Device ID of {device_name_pool_solar} is {view.get_device_id(device_name_pool_solar)}")

        #     meter_name_pool_pump = "Sydney Pool M1"
        #     meter_id_pool_pump = view.get_meter_id(meter_name_pool_pump)
        #     meter_reading_pool_pump = view.get_meter_energy(meter_id_pool_pump)
        #     print(f"Meter ID of {meter_name_pool_pump} is {meter_id_pool_pump} and reading is {meter_reading_pool_pump} Wh")

        #     temp_probe_name = "Temp Solar Return"
        #     temp_probe_id = view.get_temp_probe_id(temp_probe_name)
        #     temp_probe_reading = view.get_temp_probe_temperature(temp_probe_id)
        #     print(f"Temp Probe ID of {temp_probe_name} is {temp_probe_id} and reading is {temp_probe_reading} C")

        # except IndexError as e:
        #     print(f"Debug error: {e}")

        return view

    def _calculate_running_totals(self, view: ShellyView):
        """Calculate the running totals for each output."""
        for output in self.outputs:
            output.calculate_running_totals(view)

    def _review_run_plans(self):
        """Generate / refresh the run plan for each output."""
        for output in self.outputs:
            output.review_run_plan()

    def _evaluate_conditions(self, view: ShellyView):
        """Evaluate the conditions for each output."""
        for output in self.outputs:
            requested_action = output.evaluate_conditions(view)

            if requested_action:
                self._execute_action_on_output(output, requested_action, view)

    def _execute_action_on_output(self, output: OutputManager, requested_action: OutputAction, view: ShellyView):
        self.logger.log_message(f"Output {output.name} requests action {requested_action.type}", "detailed")

        # If the Output requests a change, post it to the ShellyWorker and wait for it to complete
        if requested_action.type in {OutputActionType.TURN_ON, OutputActionType.TURN_OFF}:
            new_state = requested_action.type == OutputActionType.TURN_ON
            # TO DO: Deal with failure to post request
            req_id = self.shelly_worker.request_output_change(output.device_output_id, new_state)

            # TO DO: Change this to make it async. Save the request ID in the OutputManager and check for completion in the main loop
            done = self.shelly_worker.wait_for_result(req_id, timeout=3.0)
            if not done:
                self.logger.log_message(f"Timed out waiting for change to output {output.device_output_name} to {requested_action.type}", "warning")

            view = self._refresh_device_statuses()  # Refresh the view after the change

        # Now tell the output to update its state based on the action taken and also deal with a requested action to just update the reason
        output.record_action_complete(requested_action, view)

    def _check_for_configuration_changes(self):
        """Reload the configuration from disk if it has changed and apply downstream changes."""
        last_modified = self.config.check_for_config_changes(self.last_config_check)
        if last_modified:
            self.last_config_check = last_modified
            self.logger.log_message("Configuration file has changed, reloading...", "detailed")
            self._save_system_state(force_post=True)  # Save state before reinitialising
            self._initialise()

    def _apply_command(self, cmd: Command) -> None:
        """Apply a command posted to the controller."""
        view = self._get_latest_status_view()
        if cmd.kind == "set_mode":
            # To DO: Push new mode into relevant Output, deal with this in the evaluation_conditions() func
            output_id = cmd.payload["output_id"]
            new_mode = AppMode(cmd.payload["mode"])
            output = self._find_output(LookupMode.ID, output_id)
            output = output[0] if output else None
            if not output:
                return

            # Set the new mode, the output will deal with it in the next tick
            # And evaluate the conditions immediately if the mode has changed
            output.set_app_mode(new_mode, view)
        elif cmd.kind == "shelly_sequence_completed":
            seq_id = cmd.payload.get("sequence_id")
            label = cmd.payload.get("label")
            ok = bool(cmd.payload.get("ok"))
            err = cmd.payload.get("error")
            if ok:
                self.logger.log_message(f"Shelly sequence {label or seq_id} completed.", "detailed")
            else:
                self.logger.log_message(f"Shelly sequence {label or seq_id} failed: {err}", "error")
            # Optional: trigger a fast evaluation tick if needed
            # self._run_scheduler_tick()

    def _have_pending_commands(self) -> bool:
        """Check if there are any pending commands in the command queue.

        Returns:
            bool: True if there are pending commands, False otherwise.
        """
        if not self.cmd_q.empty():
            return True
        return bool(self.command_pending)

    def _clear_commands(self):
        """Clear all commands in the command queue."""
        while True:
            try:
                cmd = self.cmd_q.get_nowait()
            except queue.Empty:
                break
            self._apply_command(cmd)

        self.command_pending = False

    def _save_output_consumption_data(self):
        """Save usage data for all outputs."""
        aggregated_data = []
        for output in self.outputs:
            output_data = output.get_consumption_data()
            if isinstance(output_data, list):
                aggregated_data.extend(output_data)
            else:
                aggregated_data.append(output_data)

        usage_data_file = self.config.get("General", "ConsumptionDataFile")
        if not usage_data_file:
            return
        file_path = SCCommon.select_file_location(usage_data_file)  # pyright: ignore[reportArgumentType]
        if not file_path:
            return

        # Find the ealiest date to in the aggregated data
        existing_dates = {dt.datetime.strptime(row["Date"], "%Y-%m-%d").date() for row in aggregated_data}  # noqa: DTZ007
        first_history_date = min(existing_dates) if existing_dates else DateHelper.today()

        # Read the existing data if the file exists
        existing_data = []
        if file_path.exists():
            with file_path.open("r", newline="", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    existing_data.append(row.copy())

        # Remove any rows older than the max days or newer than the first history date
        truncated_data = []
        if existing_data:
            max_days = int(self.config.get("General", "ConsumptionDataMaxDays", default=30) or 30)  # pyright: ignore[reportArgumentType]
            earliest_date = DateHelper.today() - dt.timedelta(days=max_days)  # pyright: ignore[reportArgumentType]
            truncated_data = [row for row in existing_data if row["Date"] and dt.datetime.strptime(row["Date"], "%Y-%m-%d").date() >= earliest_date and dt.datetime.strptime(row["Date"], "%Y-%m-%d").date() < first_history_date]  # pyright: ignore[reportOptionalOperand]  # noqa: DTZ007

        # Now write the data to the CSV file
        with file_path.open("w", newline="", encoding="utf-8") as csvfile:

            fieldnames = ["Date", "OutputName", "ActualHours", "TargetHours", "EnergyUsed", "TotalCost", "AveragePrice"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            # Write the existing truncated data first
            for row in truncated_data:
                writer.writerow(row)
            # Now write the new aggregated data
            for row in aggregated_data:
                writer.writerow(row)

    def _check_fatal_error_recovery(self):
        """Check for fatal errors in the system and handle them."""
        # If the prior run fails, send email that this run worked OK
        if self.logger.get_fatal_error():
            self.logger.log_message(f"{self.app_label} started successfully after a prior failure.", "summary")
            self.logger.clear_fatal_error()
            self.logger.send_email(f"{self.app_label} recovery", "Application was successfully started after a prior critical failure.")

    def _find_output(self, mode: LookupMode, identity: str) -> list[OutputManager]:
        """Return a list of all outputs that match the given criteria.

        Args:
            mode (LookupMode): The lookup mode to use.
            identity (str): The ID or name of the output to find.

        Returns:
            list[OutputManager]: The found output managers, or an empty list if not found.
        """
        if mode == LookupMode.ID:
            return [o for o in self.outputs if o.id == identity]
        if mode == LookupMode.NAME:
            return [o for o in self.outputs if o.name == identity]
        if mode == LookupMode.OUTPUT:
            return [o for o in self.outputs if o.device_output_name == identity]
        if mode == LookupMode.METER:
            return [o for o in self.outputs if o.device_meter_name == identity]
        if mode == LookupMode.INPUT:
            return [o for o in self.outputs if o.device_input_name == identity]
        return []
