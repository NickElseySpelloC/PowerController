"""The PowerController class that orchestrates power management."""
import queue
from threading import Event
from typing import Any

from sc_utility import DateHelper, SCConfigManager, SCLogger, ShellyControl

from enumerations import AppMode, Command, LightState
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
        self.logger = logger
        self.wake_event = wake_event    # The event used to interrupt the main loop
        self.cmd_q: queue.Queue[Command] = queue.Queue()    # Used to post commands into the controller's loop

        # TO DO: Remove
        self.lights: dict[str, LightState] = {
            "porch": LightState("porch", AppMode.AUTO, False, "Porch"),
            "drive": LightState("drive", AppMode.AUTO, False, "Driveway"),
        }

        # Setup the environment
        self.outputs = []   # List of output state managers, each one a OutputStateManager object.
        self.poll_interval: float = 10.0  # TO DO: Lookup via config

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

        self.initialise()

    def initialise(self):
        """(re) initialise the power controller."""
        # Create an instance of a OutputStateManager manager object for each output we're managing
        self.poll_interval: float = 10.0     # TO DO: Lookup via config

        # Loop through the Outputs configuration and setup each one.
        self.outputs.clear()

        outputs_config = self.config.get("Outputs", default=[]) or []
        try:
            for output_cfg in outputs_config:
                output_manager = OutputManager(output_cfg, self.logger, self.scheduler, self.pricing, self.shelly_control)
                self.outputs.append(output_manager)
        except RuntimeError as e:
            self.logger.log_fatal_error(f"Error initializing outputs: {e}")

    def get_state_snapshot(self) -> dict[str, Any]:
        """TO DO: Redo to return Output state information."""  # noqa: DOC201
        return {
            lid: {
                "light_id": s.light_id,
                "name": s.name or s.light_id,
                "mode": s.mode.value,
                "is_on": s.is_on,
            }
            for lid, s in self.lights.items()
        }

    def post_command(self, cmd: Command) -> None:
        """Post a command to the controller."""
        # TO DO: Update to process commands received from web app
        self.cmd_q.put(cmd)
        self.wake_event.set()

    # TO DO: Update
    def _apply_command(self, cmd: Command) -> None:
        if cmd.kind == "set_mode":
            # To DO: Push new mode into relevant Output, deal with this in the evaluation_conditions() func
            light_id = cmd.payload["light_id"]
            new_mode = AppMode(cmd.payload["mode"])
            state = self.lights.get(light_id)
            if not state:
                return
            state.mode = new_mode
            if new_mode == AppMode.ON:
                self._set_physical(light_id, True)
                state.is_on = True
            elif new_mode == AppMode.OFF:
                self._set_physical(light_id, False)
                state.is_on = False

    # TO DO: Remove
    def _set_physical(self, light_id: str, on: bool) -> None:  # noqa: FBT001, PLR6301
        print(f"[Shelly] set {light_id} to {'ON' if on else 'OFF'}")

    def run(self, stop_event: Event):
        """The main loop of the power controller.

        Args:
            stop_event (Event): The event used to stop the controller.
        """
        print("[Main] starting loop")
        while not stop_event.is_set():
            while True:
                try:
                    cmd = self.cmd_q.get_nowait()
                except queue.Empty:
                    break
                self._apply_command(cmd)
            self._run_scheduler_tick()
            self.wake_event.clear()
            self.wake_event.wait(timeout=self.poll_interval)
        print("[Main] exiting loop")

    def _run_scheduler_tick(self):
        """Do all the control processing of the main loop."""
        time_now = DateHelper.now()
        # Tell each device to update its physical state
        self._refresh_device_statuses()

        # Calculate running totals and regenerate the run_plan for each output
        self._generate_run_plans()

        # Evaluate the conditions for each output and make changes if needed
        self._evaluation_conditions()

        # Refresh the Amber price data if it's time to do so
        self.pricing.refresh_price_data_if_time()

        # TO DO: Deal with config changes including downstream objects

        # TO DO: Remove
        print(f"Main tick at {time_now.strftime('%H:%M:%S')}")

    def _refresh_device_statuses(self):
        """Refresh the status of all devices."""
        for device in self.shelly_control.devices:
            try:
                if not self.shelly_control.get_device_status(device):
                    self.logger.log_message(f"Failed to refresh status for device {device['Label']} - device offline.")
            except RuntimeError as e:
                self.logger.log_message(f"Error refreshing status for device {device['Label']}: {e}")

        # TO DO: Implement a max concurrent error handler - exit app if # number of concurrent errors exceeds limit

        # TO DO: Reconcile the output's actual state with the output.is_on state.

    def _generate_run_plans(self):
        """Generate / refresh the run plan for each output."""
        for output in self.outputs:
            output.generate_run_plan()

    def _evaluation_conditions(self):
        """Evaluate the conditions for each output."""
        # TO DO: Make sure call this for any parent outputs first
        for output in self.outputs:
            output.evaluate_conditions()
