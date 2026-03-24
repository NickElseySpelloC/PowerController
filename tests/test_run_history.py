"""Tests for RunHistory — tracking of per-output run activity and energy consumption."""

import datetime as dt
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from org_enums import RunPlanTargetHours, StateReasonOff, StateReasonOn, SystemState
from sc_utility import DateHelper

from local_enumerations import OutputStatusData
from run_history import RunHistory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_logger():
    m = MagicMock()
    m.log_message = MagicMock()
    return m


def _basic_config(target_hours=-1, days_of_history=7, min_energy_to_log=0):
    return {
        "Name": "Test Output",
        "TargetHours": target_hours,
        "DaysOfHistory": days_of_history,
        "MinEnergyToLog": min_energy_to_log,
        "MaxShortfallHours": 0,
    }


def _status(meter_reading=0.0, power_draw=0.0, is_on=False, current_price=20.0,
            target_hours=None, output_type="shelly", expect_offline=False) -> OutputStatusData:
    return OutputStatusData(
        meter_reading=meter_reading,
        power_draw=power_draw,
        is_on=is_on,
        target_hours=target_hours,
        current_price=current_price,
        output_type=output_type,
        expect_offline=expect_offline,
    )


def _make_history(config=None, saved=None) -> RunHistory:
    return RunHistory(_make_logger(), config or _basic_config(), saved)


# ---------------------------------------------------------------------------
# Static helper methods
# ---------------------------------------------------------------------------

class TestStaticHelpers:
    def test_calc_cost_basic(self):
        # 1000 Wh at 10 c/kWh = $0.10
        assert RunHistory.calc_cost(1000, 10.0) == pytest.approx(0.10, rel=1e-6)

    def test_calc_cost_zero_energy(self):
        assert RunHistory.calc_cost(0, 30.0) == 0

    def test_calc_cost_large_usage(self):
        # 5000 Wh (5 kWh) at 30 c/kWh = $1.50
        assert RunHistory.calc_cost(5000, 30.0) == pytest.approx(1.50, rel=1e-6)

    def test_calc_price_basic(self):
        # 1000 Wh used, $0.10 cost → 10 c/kWh
        assert RunHistory.calc_price(1000, 0.10) == pytest.approx(10.0, rel=1e-6)

    def test_calc_price_zero_energy(self):
        assert RunHistory.calc_price(0, 1.0) == 0

    def test_calc_price_roundtrip(self):
        energy = 3500.0  # Wh
        price_cents = 25.5  # c/kWh
        cost = RunHistory.calc_cost(energy, price_cents)
        recovered = RunHistory.calc_price(energy, cost)
        assert recovered == pytest.approx(price_cents, rel=1e-6)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestInitialisation:
    def test_empty_history_created(self):
        rh = _make_history()
        assert rh.history["DailyData"] == []
        assert rh.history["HistoryDays"] == 0

    def test_target_hours_minus_one_sets_all_hours_mode(self):
        rh = _make_history(_basic_config(target_hours=-1))
        assert rh.run_plan_target_mode == RunPlanTargetHours.ALL_HOURS

    def test_normal_target_hours_mode(self):
        cfg = {
            "Name": "Test",
            "TargetHours": 4,
            "MinHours": 2,
            "MaxHours": 6,
            "DaysOfHistory": 7,
            "MaxShortfallHours": 0,
        }
        rh = RunHistory(_make_logger(), cfg)
        assert rh.run_plan_target_mode == RunPlanTargetHours.NORMAL

    def test_saved_history_restored(self):
        rh = _make_history()
        st = _status(meter_reading=100.0, is_on=True)
        rh.start_run(SystemState.AUTO, StateReasonOn.ACTIVE_RUN_PLAN, st)
        saved = rh.history
        rh2 = _make_history(saved=saved)
        assert rh2.history["DailyData"] == saved["DailyData"]


# ---------------------------------------------------------------------------
# start_run / stop_run / get_current_run
# ---------------------------------------------------------------------------

class TestRunLifecycle:
    def test_start_run_creates_day_and_run(self):
        rh = _make_history()
        st = _status(meter_reading=500.0, is_on=True)
        rh.start_run(SystemState.AUTO, StateReasonOn.ACTIVE_RUN_PLAN, st)
        assert rh.get_current_day() is not None
        assert rh.get_current_run() is not None

    def test_start_run_twice_same_state_no_duplicate(self):
        rh = _make_history()
        st = _status(meter_reading=500.0, is_on=True)
        rh.start_run(SystemState.AUTO, StateReasonOn.ACTIVE_RUN_PLAN, st)
        rh.start_run(SystemState.AUTO, StateReasonOn.ACTIVE_RUN_PLAN, st)
        assert len(rh.get_current_day()["DeviceRuns"]) == 1

    def test_start_run_different_state_closes_old_starts_new(self):
        rh = _make_history()
        st = _status(meter_reading=500.0, is_on=True)
        rh.start_run(SystemState.AUTO, StateReasonOn.ACTIVE_RUN_PLAN, st)
        rh.start_run(SystemState.APP_OVERRIDE, StateReasonOn.APP_MODE_ON, st)
        runs = rh.get_current_day()["DeviceRuns"]
        assert len(runs) == 2
        assert runs[0]["EndTime"] is not None  # first run was closed

    def test_stop_run_sets_end_time(self):
        rh = _make_history()
        st = _status(meter_reading=500.0, is_on=True)
        rh.start_run(SystemState.AUTO, StateReasonOn.ACTIVE_RUN_PLAN, st)
        rh.stop_run(StateReasonOff.INACTIVE_RUN_PLAN, st)
        assert rh.get_current_run() is None
        last = rh.get_last_run()
        assert last["EndTime"] is not None
        assert last["ReasonStopped"] == StateReasonOff.INACTIVE_RUN_PLAN

    def test_stop_run_when_no_run_is_noop(self):
        rh = _make_history()
        st = _status()
        # Should not raise
        rh.stop_run(StateReasonOff.INACTIVE_RUN_PLAN, st)

    def test_get_current_run_none_when_stopped(self):
        rh = _make_history()
        assert rh.get_current_run() is None

    def test_get_last_run_returns_most_recent(self):
        rh = _make_history()
        st = _status(meter_reading=500.0, is_on=True)
        rh.start_run(SystemState.AUTO, StateReasonOn.ACTIVE_RUN_PLAN, st)
        rh.stop_run(StateReasonOff.INACTIVE_RUN_PLAN, st)
        rh.start_run(SystemState.APP_OVERRIDE, StateReasonOn.APP_MODE_ON, st)
        rh.stop_run(StateReasonOff.APP_MODE_OFF, st)
        last = rh.get_last_run()
        assert last["ReasonStarted"] == StateReasonOn.APP_MODE_ON


# ---------------------------------------------------------------------------
# Energy accumulation
# ---------------------------------------------------------------------------

class TestEnergyAccumulation:
    def test_energy_accumulated_across_ticks(self):
        rh = _make_history()
        # Start a run at meter reading 1000
        st1 = _status(meter_reading=1000.0, is_on=True, current_price=20.0)
        rh.start_run(SystemState.AUTO, StateReasonOn.ACTIVE_RUN_PLAN, st1)

        # Tick with higher meter reading (100 Wh used)
        st2 = _status(meter_reading=1100.0, is_on=True, current_price=20.0)
        rh.tick(st2)

        current_run = rh.get_current_run()
        assert current_run["EnergyUsed"] == pytest.approx(100.0, rel=1e-3)

    def test_cost_calculated_from_energy_and_price(self):
        rh = _make_history()
        # PriorMeterRead must be > 0 for energy calculation to work
        st1 = _status(meter_reading=5000.0, is_on=True, current_price=30.0)
        rh.start_run(SystemState.AUTO, StateReasonOn.ACTIVE_RUN_PLAN, st1)

        # 1000 Wh at 30 c/kWh = $0.30
        st2 = _status(meter_reading=6000.0, is_on=True, current_price=30.0)
        rh.tick(st2)
        rh.stop_run(StateReasonOff.INACTIVE_RUN_PLAN, st2)

        last = rh.get_last_run()
        assert last["EnergyUsed"] == pytest.approx(1000.0, rel=1e-3)
        assert last["TotalCost"] == pytest.approx(0.30, rel=1e-2)

    def test_meter_reset_detected_and_breaks_run(self):
        rh = _make_history()
        st1 = _status(meter_reading=1000.0, is_on=True)
        rh.start_run(SystemState.AUTO, StateReasonOn.ACTIVE_RUN_PLAN, st1)

        # Meter reading drops → reset detected
        st2 = _status(meter_reading=500.0, is_on=True)
        rh.tick(st2)
        # After meter reset, a new run should be started automatically
        current = rh.get_current_run()
        # Either no run or a new run (break_run was called)
        assert current is None or current["MeterReadAtStart"] == 500.0


# ---------------------------------------------------------------------------
# MinEnergyToLog filtering
# ---------------------------------------------------------------------------

class TestMinEnergyToLog:
    def test_run_below_min_energy_removed_for_meter_type(self):
        cfg = _basic_config(min_energy_to_log=50)
        rh = RunHistory(_make_logger(), cfg)
        st1 = _status(meter_reading=100.0, is_on=True, output_type="meter")
        rh.start_run(SystemState.AUTO, StateReasonOn.ACTIVE_RUN_PLAN, st1)
        # Only 10 Wh used (below the 50 Wh threshold)
        st2 = _status(meter_reading=110.0, is_on=True, output_type="meter")
        rh.stop_run(StateReasonOff.INACTIVE_RUN_PLAN, st2)
        # Run should have been removed
        day = rh.get_current_day()
        if day:
            assert len(day["DeviceRuns"]) == 0

    def test_run_above_min_energy_kept_for_meter_type(self):
        cfg = _basic_config(min_energy_to_log=50)
        rh = RunHistory(_make_logger(), cfg)
        st1 = _status(meter_reading=100.0, is_on=True, output_type="meter")
        rh.start_run(SystemState.AUTO, StateReasonOn.ACTIVE_RUN_PLAN, st1)
        # 200 Wh used (above the 50 Wh threshold)
        st2 = _status(meter_reading=300.0, is_on=True, output_type="meter")
        rh.stop_run(StateReasonOff.INACTIVE_RUN_PLAN, st2)
        day = rh.get_current_day()
        assert day is not None
        assert len(day["DeviceRuns"]) == 1

    def test_min_energy_filter_not_applied_for_shelly_type(self):
        """MinEnergyToLog is only applied to meter-type outputs, not shelly."""
        cfg = _basic_config(min_energy_to_log=500)
        rh = RunHistory(_make_logger(), cfg)
        st1 = _status(meter_reading=100.0, is_on=True, output_type="shelly")
        rh.start_run(SystemState.AUTO, StateReasonOn.ACTIVE_RUN_PLAN, st1)
        # Only 10 Wh used, but output_type="shelly" so not filtered
        st2 = _status(meter_reading=110.0, is_on=True, output_type="shelly")
        rh.stop_run(StateReasonOff.INACTIVE_RUN_PLAN, st2)
        day = rh.get_current_day()
        assert day is not None
        assert len(day["DeviceRuns"]) == 1


# ---------------------------------------------------------------------------
# get_actual_hours
# ---------------------------------------------------------------------------

class TestGetActualHours:
    def test_no_history_returns_zero(self):
        rh = _make_history()
        assert rh.get_actual_hours() == 0.0

    def test_actual_hours_accumulate(self):
        rh = _make_history()
        now = DateHelper.now()
        one_hour_ago = now - dt.timedelta(hours=1)
        st = _status(meter_reading=0.0, is_on=True)
        rh.start_run(SystemState.AUTO, StateReasonOn.ACTIVE_RUN_PLAN, st,
                     start_time=one_hour_ago)
        rh.tick(st)
        actual = rh.get_actual_hours()
        assert actual == pytest.approx(1.0, abs=0.05)


# ---------------------------------------------------------------------------
# get_energy_usage
# ---------------------------------------------------------------------------

class TestGetEnergyUsage:
    def test_empty_history_returns_zeros(self):
        rh = _make_history()
        result = rh.get_energy_usage(hours=24)
        assert result["EnergyUsed"] == 0.0
        assert result["TotalCost"] == 0.0
        assert result["AveragePrice"] == 0.0

    def test_energy_within_window_included(self):
        rh = _make_history()
        now = DateHelper.now()
        # PriorMeterRead must be > 0 for energy calculation to work
        st1 = _status(meter_reading=10000.0, is_on=True, current_price=20.0)
        rh.start_run(SystemState.AUTO, StateReasonOn.ACTIVE_RUN_PLAN, st1,
                     start_time=now - dt.timedelta(hours=2))
        st2 = _status(meter_reading=12000.0, is_on=True, current_price=20.0)
        rh.stop_run(StateReasonOff.INACTIVE_RUN_PLAN, st2,
                    stop_time=now - dt.timedelta(hours=1))
        result = rh.get_energy_usage(hours=24)
        assert result["EnergyUsed"] == pytest.approx(2000.0, rel=1e-3)


# ---------------------------------------------------------------------------
# get_daily_usage_data
# ---------------------------------------------------------------------------

class TestGetDailyUsageData:
    def test_empty_returns_empty_list(self):
        rh = _make_history()
        assert rh.get_daily_usage_data() == []

    def test_returns_row_per_day(self):
        rh = _make_history()
        st = _status(meter_reading=0.0, is_on=True)
        rh.start_run(SystemState.AUTO, StateReasonOn.ACTIVE_RUN_PLAN, st)
        rh.stop_run(StateReasonOff.INACTIVE_RUN_PLAN, st)
        data = rh.get_daily_usage_data()
        assert len(data) >= 1
        row = data[0]
        assert "Date" in row
        assert "EnergyUsed" in row
        assert "ActualHours" in row

    def test_custom_name_in_result(self):
        rh = _make_history()
        st = _status(is_on=True)
        rh.start_run(SystemState.AUTO, StateReasonOn.ACTIVE_RUN_PLAN, st)
        rh.stop_run(StateReasonOff.INACTIVE_RUN_PLAN, st)
        data = rh.get_daily_usage_data(name="CustomName")
        assert data[0]["OutputName"] == "CustomName"


# ---------------------------------------------------------------------------
# get_prior_shortfall
# ---------------------------------------------------------------------------

class TestGetPriorShortfall:
    def test_all_hours_mode_returns_zero_shortfall(self):
        rh = _make_history(_basic_config(target_hours=-1))
        shortfall, max_sf = rh.get_prior_shortfall()
        assert shortfall == 0.0
        assert max_sf == 0.0


# ---------------------------------------------------------------------------
# Midnight rollover via tick()
# ---------------------------------------------------------------------------

class TestMidnightRollover:
    def test_tick_with_same_day_no_rollover(self):
        rh = _make_history()
        st = _status(is_on=False)
        rolled = rh.tick(st)
        assert rolled is False

    def test_history_day_count_increments(self):
        rh = _make_history()
        st = _status(is_on=True, meter_reading=100.0)
        rh.start_run(SystemState.AUTO, StateReasonOn.ACTIVE_RUN_PLAN, st)
        rh.stop_run(StateReasonOff.INACTIVE_RUN_PLAN, st)
        # Simulate the next day by backdating the date on the last daily entry
        # (_have_rolled_over_to_new_day compares DailyData[-1]["Date"] to today)
        import datetime
        rh.history["DailyData"][-1]["Date"] = DateHelper.today() - datetime.timedelta(days=1)
        st2 = _status(is_on=False)
        rolled = rh.tick(st2)
        assert rolled is True
        assert rh.history["HistoryDays"] >= 1
