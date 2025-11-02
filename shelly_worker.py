from __future__ import annotations

import copy
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Optional

from sc_utility import SCConfigManager, SCLogger, ShellyControl

if TYPE_CHECKING:
    from collections.abc import Callable

# Step kinds supported by the worker
StepKind = Literal["change_output", "sleep", "refresh_status"]


@dataclass
class ShellyStep:
    kind: StepKind
    # change_output: {"output_identity": "Label", "state": True|False}
    # sleep: {"seconds": float}
    # refresh_status: {}
    params: dict[str, Any] = field(default_factory=dict)
    timeout_s: float | None = None
    retries: int = 0
    retry_backoff_s: float = 0.5


@dataclass
class ShellySequenceRequest:
    steps: list[ShellyStep]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    label: str = ""
    timeout_s: float | None = None
    on_complete: Optional["Callable[[ShellySequenceResult], None]"] = None  # optional callback  # noqa: UP037, UP045


@dataclass
class ShellySequenceResult:
    id: str
    ok: bool
    error: str | None = None
    started_ts: float = field(default_factory=time.time)
    finished_ts: float = 0.0


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

        # Command queue for changing device outputs, etc.
        self._req_q: queue.Queue[ShellySequenceRequest] = queue.Queue()
        self._results: dict[str, ShellySequenceResult] = {}
        self._results_lock = threading.Lock()
        self._result_events: dict[str, threading.Event] = {}     # NEW
        self._events_lock = threading.Lock()                     # NEW

        # Latest status snapshot (thread-safe)
        self._lookup_lock = threading.Lock()
        self._latest_status: list[dict[str, Any]] = []

    # Public API (thread-safe)
    def reinitialise_settings(self):
        shelly_settings = self.config.get_shelly_settings()
        if not isinstance(shelly_settings, dict):
            error_msg = "Shelly settings not found."
            raise TypeError(error_msg)

        # Reinitialise the ShellyControl object and get the latest status
        with self._results_lock:
            self._shelly.initialize_settings(shelly_settings, refresh_status=False)
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

    def get_latest_status(self) -> list[dict[str, Any]]:
        with self._lookup_lock:
            # shallow copy
            return list(self._latest_status)

    def request_refresh_status(self) -> str:
        """Enqueue a refresh job and return its request id.

        Pass the request ID to get_result() or wait_for_result().

        Returns:
            A request ID.
        """
        return self.submit(ShellySequenceRequest(steps=[ShellyStep("refresh_status")], label="refresh_status"))

    # Worker loop (target for ThreadManager)
    def run(self):
        self.logger.log_message("[shelly] worker started", "summary")
        try:
            while not self.stop_event.is_set():
                try:
                    req = self._req_q.get(timeout=0.5)
                except queue.Empty:
                    continue
                self._execute_request(req)
        # Allow ThreadManager to log + restart on crash
        finally:
            self.logger.log_message("[shelly] worker stopped", "summary")

    def stop(self):
        self.stop_event.set()

    # Internal execution
    def _execute_request(self, req: ShellySequenceRequest):  # noqa: PLR0915
        start = time.time()
        res = ShellySequenceResult(id=req.id, ok=False, started_ts=start)

        def run_step(step: ShellyStep):
            # Retry wrapper
            attempt = 0
            last_err: Exception | None = None
            while attempt <= step.retries and not self.stop_event.is_set():
                try:
                    if step.kind == "sleep":
                        time.sleep(float(step.params.get("seconds", 0)))
                    elif step.kind == "change_output":
                        output_identity = step.params["output_identity"]
                        state = bool(step.params.get("state", True))
                        # Example call; adjust to your ShellyControl API
                        ok = self._shelly.change_output(output_identity, state)
                        if not ok:
                            error_msg = f"change_output failed for {output_identity}"
                            raise RuntimeError(error_msg)
                    elif step.kind == "refresh_status":
                        self._refresh_all_status()
                    else:
                        raise RuntimeError(f"Unknown step kind: {step.kind}")
                    return
                except Exception as e:  # noqa: BLE001

                    # TO DO: Implement reporting of # of concurrent errors > threashold
                    # max_errors = int(self.config.get("ShellyDevices", "MaxConcurrentErrors", default=4) or 4)  # pyright: ignore[reportArgumentType]
                    # self.shelly_device_concurrent_error_count += 1

                    # # Log an issue if we exceed the max allowed errors
                    # if self.shelly_device_concurrent_error_count > max_errors and self.report_critical_errors_delay:
                    #     assert isinstance(self.report_critical_errors_delay, int)
                    #     self.logger.report_notifiable_issue(entity=f"Shelly Device {device['Label']}", issue_type="States Refresh Error", send_delay=self.report_critical_errors_delay * 60, message="Unable to get the status for this This Shelly device.")

                    last_err = e
                    attempt += 1
                    if attempt <= step.retries:
                        time.sleep(step.retry_backoff_s * attempt)
                    else:
                        raise


        try:
            for step in req.steps:
                if req.timeout_s and (time.time() - start) > req.timeout_s:
                    raise TimeoutError("sequence timeout")
                run_step(step)

            res.ok = True
        except Exception as e:
            res.ok = False
            res.error = f"{type(e).__name__}: {e}"
            self.logger.log_message(f"[shelly] sequence '{req.label or req.id}' failed: {res.error}", "error")
        finally:
            res.finished_ts = time.time()
            with self._results_lock:
                self._results[req.id] = res
            # Signal completion for this request
            with self._events_lock:
                ev = self._result_events.pop(req.id, None)
            if ev:
                ev.set()
            # Optional callback
            if req.on_complete:
                try:
                    req.on_complete(res)
                except Exception as cb_err:
                    self.logger.log_message(f"[shelly] on_complete callback error: {cb_err}", "error")
            # Wake controller
            self.wake_event.set()

    def _refresh_all_status(self):
        # Iterate configured devices; ignore expected offline
        for device in self._shelly.devices:
            try:
                self._shelly.get_device_status(device)
            except Exception as e:  # noqa: BLE001
                self.logger.log_message(f"Refresh status error for {device.get('Label')}: {e}", "error")
        # Publish snapshot, making a deep copy
        with self._lookup_lock:
            self._latest_status = copy.deepcopy(self._shelly.devices)
