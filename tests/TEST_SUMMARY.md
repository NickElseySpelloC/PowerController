# Test Suite Summary

All 235 tests pass across 8 test files.

| File | What's covered |
|---|---|
| `test_run_plan.py` | Construction, edge cases (zero hours, empty slots), price filtering, priority hours, slot consolidation, `tick()`, `get_current_slot()`, `print_info()` |
| `test_run_history.py` | Energy/cost accumulation, meter reset detection, `MinEnergyToLog` filtering, `get_actual_hours()`, `get_energy_usage()`, daily data, midnight rollover |
| `test_shelly_view.py` | Device/output/input/meter/probe lookups by name and ID, offline state, JSON snapshot, IndexError on invalid IDs |
| `test_scheduler.py` | Schedule lookups, slot price/time fields, dawn/dusk parsing (with offsets), `get_run_plan()` (NOTHING/FAILED/PARTIAL), `get_save_object()` |
| `test_ups_integration.py` | Disabled config, enabled with devices, health status for all charging/discharging scenarios, `get_ups_results()` |
| `test_shelly_worker.py` | Simulation mode initial state, request submission, `wait_for_result()`, multiple requests, callbacks, location data, reinitialisation |
| `test_output_manager.py` | `evaluate_conditions()` for all AppMode values, all RunPlanStatus values, device offline, timed revert, min on/off time, `calculate_running_totals()`, `get_save_object()` |
| `test_dataapi.py` | All 6 endpoints (`/`, `/outputs`, `/meters`, `/tempprobes`, `/energyprices`, `/all`), 503 when no data, access key via URL param / Bearer header / X-Access-Key header / env var |
| `test_webapp.py` | `GET /` (200/503/403), WebSocket initial snapshot, WebSocket commands (set_mode, invalid inputs, malformed JSON), `WebAppNotifier` bind |
