from __future__ import annotations

import copy
import queue
import threading
import time

from sc_utility import SCConfigManager, SCLogger, ShellyControl

from local_enumerations import (
    ShellySequenceRequest,
    ShellySequenceResult,
    ShellyStatus,
    ShellyStep,
    StepKind,
)


class ShellyWorker:
    """Owns ShellyControl. Processes step sequences and periodic status refreshes."""

    def __init__(self, config: SCConfigManager, logger: SCLogger, wake_event: threading.Event):
        self.config = config
        self.logger = logger
        self.wake_event = wake_event
        self.stop_event = threading.Event()

        shelly_settings = self.config.get_shelly_settings()
        if not isinstance(shelly_settings, dict):
            error_msg = "Shelly settings not found."
            raise TypeError(error_msg)

        # Create an instance of the ShellyControl and refresh the status
        self._shelly = ShellyControl(logger, shelly_settings, wake_event)

        # Error reporting
        self.concurrent_error_count: int = 0  # Number of concurrent errors
        self.max_shelly_errors: int = int(self.config.get("ShellyDevices", "MaxConcurrentErrors", default=4) or 4)  # pyright: ignore[reportArgumentType]
        self.report_critical_errors_delay = config.get("General", "ReportCriticalErrorsDelay", default=None)
        if isinstance(self.report_critical_errors_delay, (int, float)):
            self.report_critical_errors_delay = round(self.report_critical_errors_delay, 0)
        else:
            self.report_critical_errors_delay = None

        # Command queue for changing device outputs, etc.
        self._req_q: queue.Queue[ShellySequenceRequest] = queue.Queue()
        self._results: dict[str, ShellySequenceResult] = {}
        self._results_lock = threading.Lock()
        self._result_events: dict[str, threading.Event] = {}     # NEW
        self._events_lock = threading.Lock()                     # NEW

        # Latest status snapshot (thread-safe)
        self._lookup_lock = threading.Lock()
        self._latest_status: ShellyStatus = ShellyStatus(devices=[], outputs=[], inputs=[], meters=[], temp_probes=[])
        self._location_data: dict[str, dict] = {}

        # Set the inital setting for online status. This will be updated in _refresh_all_status()
        self.all_shelly_devices_online = True
        with self._lookup_lock:
            for device in self._shelly.devices:
                if not device.get("Online", False):
                    self.all_shelly_devices_online = False

        # Immedaietly save the latest status so that we always have something to return
        self._save_latest_status()

    # Public API (thread-safe)
    def reinitialise_settings(self):
        shelly_settings = self.config.get_shelly_settings()
        if not isinstance(shelly_settings, dict):
            error_msg = "Shelly settings not found."
            raise TypeError(error_msg)

        # Reinitialise the ShellyControl object and get the latest status
        with self._results_lock:
            self._shelly.initialize_settings(shelly_settings, refresh_status=False)
            self.concurrent_error_count = 0
        self._refresh_all_status()

    def submit(self, req: ShellySequenceRequest) -> str:
        # Create a completion event for this request
        ev = threading.Event()
        with self._events_lock:
            self._result_events[req.id] = ev
        self._req_q.put(req)
        return req.id

    def get_result(self, req_id: str) -> ShellySequenceResult | None:
        with self._results_lock:
            return self._results.get(req_id)

    def wait_for_result(self, req_id: str, timeout: float | None = None) -> bool:
        """Block until the specific request completes or timeout.

        Returns:
            True if completed.
        """
        with self._events_lock:
            ev = self._result_events.get(req_id)
        if ev is None:
            # Unknown id or already collected; consider it done
            return True
        ok = ev.wait(timeout=timeout)
        return ok

    def get_latest_status(self) -> ShellyStatus:
        with self._lookup_lock:
            return self._latest_status

    def get_location_info(self) -> dict[str, dict]:
        """Get the latest device location information.

        Returns:
             A dict of location data, keyed by Shelly device name.
        """
        with self._lookup_lock:
            return self._location_data

    def request_refresh_status(self) -> str:
        """Enqueue a refresh job and return its request id.

        Pass the request ID to get_result() or wait_for_result().

        Returns:
            A request ID.
        """
        sequence_request = ShellySequenceRequest(steps=[ShellyStep(StepKind.REFRESH_STATUS)], label="refresh_status")
        return self.submit(sequence_request)

    # def request_output_change(self, output_id: int, output_state: bool, on_complete: Callable[[ShellySequenceResult], None] | None = None) -> str:
    #     """Enqueue a change output job and return its request id.

    #     Args:
    #         output_id (int): The device output identity.
    #         output_state (bool): The desired output state.
    #         on_complete: Optional callback function to invoke when the sequence completes.

    #     Returns:
    #         A request ID.
    #     """
    #     steps = [
    #         ShellyStep(StepKind.CHANGE_OUTPUT, {"output_identity": output_id, "state": output_state}, retries=2, retry_backoff_s=1.0),
    #     ]
    #     label = f"change_output_{output_id}_to_{output_state}"
    #     sequence_request = ShellySequenceRequest(
    #         steps=steps,
    #         label=label,
    #         timeout_s=10.0,
    #         on_complete=on_complete
    #     )
    #     return self.submit(sequence_request)

    def request_device_location(self, device_name: str) -> str:
        """Enqueue a get location job and return its request id.

        Args:
            device_name (str): The device identity.

        Returns:
            A request ID.
        """
        steps = [
            ShellyStep(StepKind.GET_LOCATION, {"device_identity": device_name}, retries=1, retry_backoff_s=1.0),
        ]
        label = f"get_location_for_{device_name}"
        sequence_request = ShellySequenceRequest(
            steps=steps,
            label=label,
            timeout_s=10.0
        )
        return self.submit(sequence_request)

    # Worker loop (target for ThreadManager)
    def run(self):
        self.logger.log_message("Shelly worker started", "detailed")
        try:
            while not self.stop_event.is_set():
                try:
                    req = self._req_q.get(timeout=0.5)
                except queue.Empty:
                    continue
                self._execute_request(req)
        # Allow ThreadManager to log + restart on crash
        finally:
            self.logger.log_message("Shelly worker shutdown complete.", "detailed")

    def stop(self):
        self.stop_event.set()

    # Internal execution
    def _execute_request(self, req: ShellySequenceRequest):
        """Execute a sequence of ShellyStep steps.

        Args:
            req (ShellySequenceRequest): The request to execute.
        """
        start = time.time()
        res = ShellySequenceResult(id=req.id, ok=False, started_ts=start)
        reinitialise_reqd = False

        try:
            for step in req.steps:
                if req.timeout_s and (time.time() - start) > req.timeout_s:
                    res.ok = False
                    res.error = "sequence timeout"
                else:
                    self._run_step(step)
            # If we get here without exceptions, the sequence succeeded
            res.ok = True
        except (RuntimeError, TimeoutError) as e:   # _run_step() can raised a knonw exception. Retries have been exceeded.
            res.ok = False
            res.error = f"{type(e).__name__}: {e}"

        finally:
            res.finished_ts = time.time()
            with self._results_lock:
                self._results[req.id] = res

            # Deal with logging errors
            if not res.ok:
                self.logger.log_message(f"[shelly] sequence '{req.label or req.id}' failed: {res.error}", "error")

                # Log an issue if we exceed the max allowed errors
                self.concurrent_error_count += 1
                if self.concurrent_error_count > self.max_shelly_errors and self.report_critical_errors_delay:
                    assert isinstance(self.report_critical_errors_delay, int)
                    self.logger.report_notifiable_issue(entity="Shelly Worker Sequence Runner", issue_type="Sequence Failed", send_delay=self.report_critical_errors_delay * 60, message=str(res.error))

            # Signal completion for this request
            with self._events_lock:
                ev = self._result_events.pop(req.id, None)
            if ev:
                ev.set()
            # Optional callback
            if req.on_complete:
                try:
                    req.on_complete(res)
                except Exception as cb_err:  # noqa: BLE001
                    self.logger.log_message(f"[shelly] on_complete callback error: {cb_err}", "error")

            if reinitialise_reqd:
                self.reinitialise_settings()

                # Make sure we don't repeat this block again
                self.all_shelly_devices_online = True

            # Wake controller
            self.wake_event.set()

    def _run_step(self, step: ShellyStep):
        """Run a single ShellyStep with retries as needed.

        Args:
            step (ShellyStep): The step to run.

        Raises:
            TimeoutError: If the step times out after retries.
            RuntimeError: If a non-recoverable error occurs.

        Returns:
            bool: True if reinitialisation of ShellyControl is required.
        """
        attempt = 0
        reinitialise_reqd = False
        while attempt <= step.retries and not self.stop_event.is_set():
            error_msg = None
            try:
                if step.kind == StepKind.SLEEP:    # Sleep for the specified duration
                    self.logger.log_message(f"ShellyWorker sleeping for {step.params.get('seconds', 0)} seconds", "debug")
                    time.sleep(float(step.params.get("seconds", 0)))

                elif step.kind == StepKind.CHANGE_OUTPUT:  # Change the output state of a device
                    output_identity = step.params["output_identity"]
                    state = bool(step.params.get("state", True))
                    self.logger.log_message(f"ShellyWorker changing output {output_identity} to state {state}", "debug")
                    result, did_change = self._shelly.change_output(output_identity, state)
                    if not result:
                        error_msg = f"change_output failed for {output_identity}"
                        raise TimeoutError(error_msg)  # noqa: TRY301
                    if not did_change:
                        self.logger.log_message(f"Requested changing output {output_identity} to {state} but it was already in that state.", "warning")

                elif step.kind == StepKind.REFRESH_STATUS:   # Refresh status for all devices
                    self.logger.log_message("ShellyWorker refreshing all device status", "debug")
                    reinitialise_reqd = self._refresh_all_status()

                elif step.kind == StepKind.GET_LOCATION:   # Get location info for a device
                    device_name = step.params["device_identity"]
                    self.logger.log_message(f"ShellyWorker getting location info for device {device_name}", "debug")
                    loc_info = self._shelly.get_device_location(device_name)
                    if loc_info:
                        with self._lookup_lock:
                            self._location_data[device_name] = copy.deepcopy(loc_info)

                else:
                    error_msg = f"Unknown step kind: {step.kind}"
                    raise RuntimeError(error_msg)  # noqa: TRY301
            except TimeoutError as e:   # A ShellyControl timeout
                attempt += 1
                if attempt <= step.retries:
                    time.sleep(step.retry_backoff_s * attempt)
                else:
                    timeout_msg = f"Step '{step.kind}' timed out after {attempt} attempts: {e}"
                    raise TimeoutError(timeout_msg) from e
            except RuntimeError as e:     # A more serious ShellyControl error
                runtime_msg = f"Step '{step.kind}' threw RunTime error - skipping retry attempts: {e}"
                raise RuntimeError(runtime_msg) from e
            else:
                # If there were no exceptions, we're done. Return reinitialise_reqd flag.
                return reinitialise_reqd

        return reinitialise_reqd

    def _refresh_all_status(self):
        """Get the latest status for each device in turn, calling the ShellyControl.get_device_status() method.

        Raises:
            TimeoutError: If unable to get status for any device not expected to be offline.
            RuntimeError: If unable to get status for any device.

        Returns:
            bool: True if reinitialisation of ShellyControl is required (all devices now online
        """
        reinitialise_reqd = False
        offline_device = False
        for device in self._shelly.devices:
            with self._lookup_lock:     # Get the relevant values for this device
                device_label = device.get("Label")
                expect_offline = device.get("ExpectOffline", False)

            try:
                if not self._shelly.get_device_status(device) and not expect_offline:
                    self.logger.log_message(f"Failed to refresh status for device {device_label} - device offline.", "error")
            except TimeoutError as e:
                if expect_offline:
                    self.logger.log_message(f"Device {device_label} is offline as expected.", "detailed")
                else:
                    error_msg = f"Failed to refresh status for device {device_label} - device offline."
                    self.logger.log_message(error_msg, "error")
                    raise TimeoutError(error_msg) from e
            except RuntimeError as e:
                error_msg = f"Error refreshing status for device {device_label}: {e}"
                self.logger.log_message(error_msg, "error")
                raise RuntimeError(error_msg) from e
            else:
                # Finally, see if this device is online
                if not device.get("Online", False):
                    offline_device = True

        # Now see if we need to reinitialise the Shelly controller because all devices are now online and they weren't previously
        if not offline_device and not self.all_shelly_devices_online:
            self.logger.log_message("All Shelly devices are now online, requesting reinitialise settings", "detailed")
            reinitialise_reqd = True

        # Publish snapshot, making a deep copy
        self._save_latest_status()

        return reinitialise_reqd

    def _save_latest_status(self):
        """Save a deep copy of the latest device status for thread-safe access."""
        with self._lookup_lock:
            self._latest_status = ShellyStatus(
                devices=copy.deepcopy(self._shelly.devices),
                outputs=copy.deepcopy(self._shelly.outputs),
                inputs=copy.deepcopy(self._shelly.inputs),
                meters=copy.deepcopy(self._shelly.meters),
                temp_probes=copy.deepcopy(self._shelly.temp_probes)
            )
