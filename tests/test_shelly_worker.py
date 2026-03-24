"""Tests for ShellyWorker using simulated Shelly devices."""

import sys
import threading
import time
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from local_enumerations import ShellySequenceRequest, ShellyStep, StepKind
from shelly_view import ShellyView

# ---------------------------------------------------------------------------
# All tests use the session-scoped shelly_worker fixture from conftest.py
# We run the worker thread per-test (start/stop) to avoid cross-test state.
# ---------------------------------------------------------------------------


@pytest.fixture
def running_worker(shelly_worker):
    """Start the worker thread; stop it after the test."""
    shelly_worker.stop_event.clear()  # Reset so run() loop works after a prior stop()
    t = threading.Thread(target=shelly_worker.run, daemon=True, name="shelly_worker")
    t.start()
    yield shelly_worker
    shelly_worker.stop()
    t.join(timeout=5.0)


# ---------------------------------------------------------------------------
# Initial state (no thread required)
# ---------------------------------------------------------------------------

class TestInitialState:
    def test_worker_has_latest_status_on_creation(self, shelly_worker):
        status = shelly_worker.get_latest_status()
        assert status is not None

    def test_initial_status_has_network_rack_device(self, shelly_worker):
        status = shelly_worker.get_latest_status()
        names = [d["Name"] for d in status.devices]
        assert "Network Rack" in names

    def test_initial_status_has_expected_outputs(self, shelly_worker):
        status = shelly_worker.get_latest_status()
        output_names = [o["Name"] for o in status.outputs]
        assert "Network Rack O1" in output_names
        assert "Network Rack O2" in output_names

    def test_initial_status_has_temp_probe(self, shelly_worker):
        status = shelly_worker.get_latest_status()
        probe_names = [p["Name"] for p in status.temp_probes]
        assert "Network Rack" in probe_names

    def test_shelly_view_wraps_status_correctly(self, shelly_worker):
        status = shelly_worker.get_latest_status()
        view = ShellyView(snapshot=status)
        assert view.get_device_id("Network Rack") != 0
        assert view.get_output_id("Network Rack O1") != 0


# ---------------------------------------------------------------------------
# Request submission and result retrieval (worker thread running)
# ---------------------------------------------------------------------------

class TestRequestExecution:
    def test_submit_returns_request_id(self, running_worker):
        req = ShellySequenceRequest(
            steps=[ShellyStep(StepKind.REFRESH_STATUS)],
            label="test_refresh",
        )
        req_id = running_worker.submit(req)
        assert isinstance(req_id, str)
        assert len(req_id) > 0

    def test_wait_for_result_completes(self, running_worker):
        req = ShellySequenceRequest(
            steps=[ShellyStep(StepKind.REFRESH_STATUS)],
            label="test_wait",
        )
        req_id = running_worker.submit(req)
        completed = running_worker.wait_for_result(req_id, timeout=5.0)
        assert completed is True

    def test_result_is_ok_after_refresh(self, running_worker):
        req = ShellySequenceRequest(
            steps=[ShellyStep(StepKind.REFRESH_STATUS)],
            label="test_result_ok",
        )
        req_id = running_worker.submit(req)
        running_worker.wait_for_result(req_id, timeout=5.0)
        result = running_worker.get_result(req_id)
        assert result is not None
        assert result.ok is True

    def test_status_updated_after_refresh(self, running_worker):
        req_id = running_worker.request_refresh_status()
        running_worker.wait_for_result(req_id, timeout=5.0)
        status = running_worker.get_latest_status()
        # Status should still have our simulated device
        assert any(d["Name"] == "Network Rack" for d in status.devices)

    def test_multiple_requests_all_complete(self, running_worker):
        ids = []
        for _ in range(3):
            req = ShellySequenceRequest(
                steps=[ShellyStep(StepKind.REFRESH_STATUS)],
                label="multi_refresh",
            )
            ids.append(running_worker.submit(req))

        for req_id in ids:
            assert running_worker.wait_for_result(req_id, timeout=5.0) is True

    def test_callback_invoked_on_completion(self, running_worker):
        called_with = []

        def on_done(result):
            called_with.append(result)

        req = ShellySequenceRequest(
            steps=[ShellyStep(StepKind.REFRESH_STATUS)],
            label="callback_test",
            on_complete=on_done,
        )
        req_id = running_worker.submit(req)
        running_worker.wait_for_result(req_id, timeout=5.0)
        # Give the callback a moment to fire
        time.sleep(0.2)
        assert len(called_with) == 1
        assert called_with[0].ok is True


# ---------------------------------------------------------------------------
# Location data
# ---------------------------------------------------------------------------

class TestLocationData:
    def test_get_location_info_returns_dict(self, shelly_worker):
        loc = shelly_worker.get_location_info()
        assert isinstance(loc, dict)

    def test_request_device_location_submits_and_completes(self, running_worker):
        req_id = running_worker.request_device_location("Network Rack")
        assert isinstance(req_id, str)
        # The request may succeed or fail depending on simulation capability,
        # but it must complete within the timeout.
        completed = running_worker.wait_for_result(req_id, timeout=5.0)
        assert completed is True


# ---------------------------------------------------------------------------
# Reinitialisation
# ---------------------------------------------------------------------------

class TestReinitialise:
    def test_reinitialise_does_not_crash(self, shelly_worker):
        """reinitialise_settings() should not raise with the test config."""
        shelly_worker.reinitialise_settings()
        status = shelly_worker.get_latest_status()
        assert status is not None
