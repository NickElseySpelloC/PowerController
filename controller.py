"""The PowerController class that orchestrates power management."""
import queue
from pathlib import Path
from threading import Event

from org_enums import AppMode
from sc_utility import (
    DateHelper,
    JSONEncoder,
    SCCommon,
    SCConfigManager,
    SCLogger,
    ShellyControl,
)

from external_services import ExternalServiceHelper
from local_enumerations import Command, LookupMode
from outputs import OutputManager
from pricing import PricingManager
from scheduler import Scheduler


class PowerController:
    """The PowerController class that orchestrates power management."""
    def __init__(self, config: SCConfigManager, logger: SCLogger, wake_event: Event):
        """Initializes the PowerController.

        Args:
            config (SCConfigManager): The configuration manager for the system.
            logger (SCLogger): The logger for the system.
            wake_event (Event): The event used to wake the controller.
        """
        self.config = config
        self.last_config_check = DateHelper.now()
        self.logger = logger
        self.external_service_helper = ExternalServiceHelper(config, logger)
        self.viewer_website_last_post = None
        self.wake_event = wake_event    # The event used to interrupt the main loop
        self.cmd_q: queue.Queue[Command] = queue.Queue()    # Used to post commands into the controller's loop
        self.shelly_device_concurrent_error_count = 0
        self.report_critical_errors_delay = config.get("General", "ReportCriticalErrorsDelay", default=None)
        if isinstance(self.report_critical_errors_delay, (int, float)):
            self.report_critical_errors_delay = round(self.report_critical_errors_delay, 0)
        else:
            self.report_critical_errors_delay = None

        # Setup the environment
        self.outputs = []   # List of output state managers, each one a OutputStateManager object.
        self.poll_interval = 10.0

        # Create an instance of the ShellyControl class
        shelly_settings = self.config.get_shelly_settings()
        if shelly_settings is None:
            logger.log_fatal_error("No Shelly settings found in the configuration file.")
            return
        try:
            assert isinstance(shelly_settings, dict)
            self.shelly_control = ShellyControl(logger, shelly_settings, self.wake_event)
        except RuntimeError as e:
            logger.log_fatal_error(f"Shelly control initialization error: {e}")
            return

        # Create the two run_planner types
        self.scheduler = Scheduler(self.config, self.logger, self.shelly_control)
        self.pricing = PricingManager(self.config, self.logger)

        # See if we have a system state file to load
        state_data = self._load_system_state()

        self.initialise(state_data)
        self.logger.log_message("Power controller startup complete.", "summary")

    def initialise(self, saved_state: dict | None = None):
        """(re) initialise the power controller."""
        self.poll_interval = int(self.config.get("General", "PollingInterval", default=30) or 30)  # pyright: ignore[reportArgumentType]
        self.webapp_refresh = int(self.config.get("Website", "PageAutoRefresh", default=10) or 10)  # pyright: ignore[reportArgumentType]
        self.app_label = self.config.get("General", "Label", default="PowerController")

        if not saved_state:
            # Reinitialise the Shelly controller
            shelly_settings = self.config.get_shelly_settings()
            self.shelly_control.initialize_settings(shelly_settings, refresh_status=True)

        # Confirm that the configured output names are unique
        output_names = [o["Name"] for o in self.config.get("Outputs", default=[]) or []]
        if len(output_names) != len(set(output_names)):
            self.logger.log_fatal_error("Output names must be unique.")
            return

        # Loop through each output read from the config file
        # Create an instance of a OutputStateManager manager object for each output we're managing
        outputs_config = self.config.get("Outputs", default=[]) or []
        try:
            for output_cfg in outputs_config:
                # Search for an existing output with the same name and update it if found
                if any(o.name == output_cfg.get("Name") for o in self.outputs):
                    existing_output = next(o for o in self.outputs if o.name == output_cfg.get("Name"))
                    existing_output.initialise(output_cfg)
                    continue

                # See if we can find saved state for this output
                output_state = None
                if saved_state and "Outputs" in saved_state:
                    output_state = next((o for o in saved_state["Outputs"] if o.get("Name") == output_cfg.get("Name")), None)

                # Create a new output manager
                output_manager = OutputManager(output_cfg, self.config, self.logger, self.scheduler, self.pricing, self.shelly_control, output_state)
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

    def save_system_state(self, force_post: bool = False):  # noqa: FBT001, FBT002
        """Saves the system state to disk.

        Args:
            force_post (bool): If True, force posting the state to the web viewer.
        """
        system_state_path = self._get_system_state_path()
        if not system_state_path:
            return

        try:
            save_object = {
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
                        "StateFileType": "PowerController",
                        "DeviceName": f"{self.app_label} - {output.name}",
                        "SaveTime": DateHelper.now(),
                        "Output": output.get_save_object(),
                        "Scheduler": self.scheduler.get_save_object(output.schedule),
                    }
                    self.external_service_helper.post_state_to_web_viewer(post_object)
                self.viewer_website_last_post = DateHelper.now()

    def get_webapp_data(self) -> dict:
        """Returns a dict object with a snapshot of the current state of all outputs.

        Returns:
            dict: The state snapshot containing theoutputs.
        """
        global_data = {
            "access_key": self.config.get("Website", "AccessKey"),
            "AppLabel": self.app_label,
            "PollInterval": self.webapp_refresh,
        }

        outputs_data = {
            output.id: output.get_webapp_data()
            for output in self.outputs
        }

        return_dict = {
            "global": global_data,
            "outputs": outputs_data,
        }

        return return_dict

    def post_command(self, cmd: Command) -> None:
        """Post a command to the controller from the web app."""
        self.cmd_q.put(cmd)
        self.logger.log_message(f"Posted command to controller:\n {cmd}", "debug")
        self.wake_event.set()

    def _apply_command(self, cmd: Command) -> None:
        """Apply a command posted to the controller."""
        if cmd.kind == "set_mode":
            # To DO: Push new mode into relevant Output, deal with this in the evaluation_conditions() func
            output_id = cmd.payload["output_id"]
            new_mode = AppMode(cmd.payload["mode"])
            output = self._find_output(LookupMode.ID, output_id)
            output = output[0] if output else None
            if not output:
                return

            # Set the new mode, the output will deal with it in the next tick
            self.logger.log_message(f"Applying new mode {new_mode} to output {output_id}", "debug")
            output.app_mode = new_mode

            # And evaluate the conditions immediately
            output.evaluate_conditions()

    def run(self, stop_event: Event):
        """The main loop of the power controller.

        Args:
            stop_event (Event): The event used to stop the controller.
        """
        self.logger.log_message("Power controller starting main control loop.", "detailed")

        if self.run_self_tests():
            return

        while not stop_event.is_set():
            while True:
                print(f"Main tick at {DateHelper.now().strftime('%H:%M:%S')}")
                try:
                    cmd = self.cmd_q.get_nowait()
                except queue.Empty:
                    break
                self._apply_command(cmd)
            self._run_scheduler_tick()
            self.wake_event.clear()
            self.wake_event.wait(timeout=self.poll_interval)

        self.shutdown()

    def _run_scheduler_tick(self):
        """Do all the control processing of the main loop."""
        # Tell each device to update its physical state
        self._refresh_device_statuses()

        # Calculate running totals and regenerate the run_plan for each output
        self._generate_run_plans()

        # Evaluate the conditions for each output and make changes if needed
        self._evaluate_conditions()

        # Refresh the Amber price data if it's time to do so
        self.pricing.refresh_price_data_if_time()

        # Deal with config changes including downstream objects
        self._check_for_configuration_changes()

        # Save the system state to disk
        self.save_system_state()

        # Ping the heartbeat monitor - this function takes care of frequency checks
        self.external_service_helper.ping_heatbeat()

        # Check for fatal error recovery
        self._check_fatal_error_recovery()

    def _refresh_device_statuses(self):
        """Refresh the status of all devices."""
        max_errors = int(self.config.get("ShellyDevices", "MaxConcurrentErrors", default=4) or 4)  # pyright: ignore[reportArgumentType]
        for device in self.shelly_control.devices:
            try:
                if not self.shelly_control.get_device_status(device):
                    self.logger.log_message(f"Failed to refresh status for device {device['Label']} - device offline.")
            except RuntimeError as e:
                self.logger.log_message(f"Error refreshing status for device {device['Label']}: {e}", "error")
                self.shelly_device_concurrent_error_count += 1

                # Log an issue if we exceed the max allowed errors
                if self.shelly_device_concurrent_error_count > max_errors and self.report_critical_errors_delay:
                    assert isinstance(self.report_critical_errors_delay, int)
                    self.logger.report_notifiable_issue(entity=f"Shelly Device {device['Label']}", issue_type="States Refresh Error", send_delay=self.report_critical_errors_delay * 60, message="Unable to get the status for this This Shelly device.")

    def _generate_run_plans(self):
        """Generate / refresh the run plan for each output."""
        for output in self.outputs:
            output.generate_run_plan()

    def _evaluate_conditions(self):
        """Evaluate the conditions for each output."""
        # Do the parents first
        for output in self.outputs:
            if output.is_parent:
                output.evaluate_conditions()

        # Now do the children
        for output in self.outputs:
            if not output.is_parent:
                output.evaluate_conditions()

    def _check_for_configuration_changes(self):
        """Reload the configuration from disk if it has changed and apply downstream changes."""
        last_modified = self.config.check_for_config_changes(self.last_config_check)
        if last_modified:
            self.last_config_check = last_modified
            self.logger.log_message("Configuration file has changed, reloading...", "debug")
            self.initialise()

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

    def shutdown(self):
        """Shutdown the power controller, turning off outputs if configured to do so."""
        self.logger.log_message("Interrupt received, shutting down power controller...", "summary")
        for output in self.outputs:
            output.shutdown()

        self.save_system_state(force_post=True)

    def print_to_console(self, message: str):
        """Print a message to the console if PrintToConsole is enabled.

        Args:
            message (str): The message to print.
        """
        if self.config.get("General", "PrintToConsole", default=False):
            print(message)

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
