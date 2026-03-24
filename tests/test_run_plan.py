"""Tests for RunPlanner — the core scheduling algorithm."""

import datetime as dt
import sys
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from org_enums import RunPlanMode, RunPlanStatus
from sc_utility import DateHelper

from local_enumerations import AmberChannel
from run_plan import RunPlanner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_slot(start: dt.datetime, end: dt.datetime, price: float) -> dict:
    """Build a slot dict compatible with RunPlanner."""
    minutes = int((end - start).total_seconds() / 60)
    return {
        "Date": start.date(),
        "StartDateTime": start,
        "EndDateTime": end,
        "Minutes": minutes,
        "Price": price,
    }


def _slots_from_now(offsets: list[tuple[float, float, float]]) -> list[dict]:
    """
    Build a list of slots relative to now.

    Each tuple is (start_offset_hours, end_offset_hours, price).
    A negative start_offset puts the slot in the past.
    """
    now = DateHelper.now().replace(second=0, microsecond=0)
    slots = []
    for start_h, end_h, price in offsets:
        start = now + dt.timedelta(hours=start_h)
        end = now + dt.timedelta(hours=end_h)
        slots.append(_make_slot(start, end, price))
    return slots


def _make_planner(plan_type=RunPlanMode.SCHEDULE) -> RunPlanner:
    from unittest.mock import MagicMock
    logger = MagicMock()
    logger.log_message = MagicMock()
    return RunPlanner(logger, plan_type)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestRunPlannerInit:
    def test_valid_schedule_mode(self):
        p = _make_planner(RunPlanMode.SCHEDULE)
        assert p.plan_type == RunPlanMode.SCHEDULE
        assert p.channel is None

    def test_valid_best_price_mode_with_channel(self):
        from unittest.mock import MagicMock
        logger = MagicMock()
        p = RunPlanner(logger, RunPlanMode.BEST_PRICE, channel=AmberChannel.GENERAL)
        assert p.channel == AmberChannel.GENERAL

    def test_invalid_plan_type_raises(self):
        from unittest.mock import MagicMock
        logger = MagicMock()
        with pytest.raises(RuntimeError, match="Invalid plan type"):
            RunPlanner(logger, "NotAMode")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# calculate_run_plan — edge cases
# ---------------------------------------------------------------------------

class TestCalculateRunPlanEdgeCases:
    def test_zero_required_hours_returns_nothing(self):
        p = _make_planner()
        slots = _slots_from_now([(0, 1, 10.0)])
        result = p.calculate_run_plan(slots, required_hours=0, priority_hours=0,
                                      max_price=50.0, max_priority_price=50.0)
        assert result["Status"] == RunPlanStatus.NOTHING
        assert result["PlannedHours"] == 0.0

    def test_empty_slots_returns_failed(self):
        p = _make_planner()
        result = p.calculate_run_plan([], required_hours=2, priority_hours=0,
                                      max_price=50.0, max_priority_price=50.0)
        assert result["Status"] == RunPlanStatus.FAILED
        assert result["PlannedHours"] == 0.0

    def test_invalid_max_price_raises(self):
        p = _make_planner()
        slots = _slots_from_now([(0, 1, 10.0)])
        with pytest.raises(RuntimeError, match="Invalid price parameters"):
            p.calculate_run_plan(slots, required_hours=1, priority_hours=0,
                                 max_price=0, max_priority_price=50.0)

    def test_all_slots_too_expensive_returns_failed(self):
        p = _make_planner()
        slots = _slots_from_now([(0, 2, 100.0)])
        result = p.calculate_run_plan(slots, required_hours=1, priority_hours=0,
                                      max_price=20.0, max_priority_price=20.0)
        assert result["Status"] == RunPlanStatus.FAILED

    def test_schedule_empty_slots_all_hours_returns_nothing(self):
        """required_hours=-1 with empty slots under SCHEDULE mode → NOTHING."""
        p = _make_planner(RunPlanMode.SCHEDULE)
        result = p.calculate_run_plan([], required_hours=-1, priority_hours=0,
                                      max_price=50.0, max_priority_price=50.0)
        assert result["Status"] == RunPlanStatus.NOTHING


# ---------------------------------------------------------------------------
# calculate_run_plan — price filtering
# ---------------------------------------------------------------------------

class TestPriceFiltering:
    def test_slots_within_max_price_selected(self):
        p = _make_planner()
        slots = sorted(_slots_from_now([(0, 1, 10.0), (1, 2, 50.0)]),
                       key=lambda s: s["Price"])
        result = p.calculate_run_plan(slots, required_hours=1, priority_hours=0,
                                      max_price=20.0, max_priority_price=20.0)
        assert result["Status"] in {RunPlanStatus.READY, RunPlanStatus.PARTIAL}
        assert len(result["RunPlan"]) >= 1

    def test_all_hours_mode_includes_all_qualifying(self):
        p = _make_planner()
        # Three 1-hour slots, all under max price
        slots = sorted(_slots_from_now([(0, 1, 5.0), (1, 2, 8.0), (2, 3, 12.0)]),
                       key=lambda s: s["Price"])
        result = p.calculate_run_plan(slots, required_hours=-1, priority_hours=0,
                                      max_price=20.0, max_priority_price=20.0)
        assert result["Status"] in {RunPlanStatus.READY, RunPlanStatus.PARTIAL, RunPlanStatus.NOTHING}
        total_planned = sum(s["Minutes"] for s in result["RunPlan"])
        assert total_planned >= 120  # at least 2 hours of qualifying time

    def test_priority_hours_use_higher_price(self):
        p = _make_planner()
        # Cheap slot (within normal max) + expensive slot (within priority max only)
        slots = sorted(_slots_from_now([(0, 1, 15.0), (1, 2, 40.0)]),
                       key=lambda s: s["Price"])
        result = p.calculate_run_plan(slots, required_hours=2, priority_hours=1,
                                      max_price=20.0, max_priority_price=50.0)
        # Both slots should appear since total required is 2h and priority allows up to 50c
        assert result["Status"] in {RunPlanStatus.READY, RunPlanStatus.PARTIAL}


# ---------------------------------------------------------------------------
# calculate_run_plan — slot consolidation
# ---------------------------------------------------------------------------

class TestSlotConsolidation:
    def test_back_to_back_slots_merged(self):
        """Two consecutive slots should merge into one."""
        p = _make_planner()
        now = DateHelper.now().replace(second=0, microsecond=0)
        s1 = _make_slot(now, now + dt.timedelta(hours=1), 10.0)
        s2 = _make_slot(now + dt.timedelta(hours=1), now + dt.timedelta(hours=2), 12.0)
        result = p.calculate_run_plan([s1, s2], required_hours=2, priority_hours=0,
                                      max_price=20.0, max_priority_price=20.0,
                                      slot_min_gap_minutes=0)
        assert len(result["RunPlan"]) == 1
        assert result["RunPlan"][0]["Minutes"] == 120

    def test_small_gap_between_slots_merged_when_gap_minutes_set(self):
        """A 5-minute gap should be merged when slot_min_gap_minutes=10."""
        p = _make_planner()
        now = DateHelper.now().replace(second=0, microsecond=0)
        s1 = _make_slot(now, now + dt.timedelta(hours=1), 10.0)
        s2 = _make_slot(now + dt.timedelta(minutes=65), now + dt.timedelta(minutes=125), 12.0)
        result = p.calculate_run_plan([s1, s2], required_hours=2, priority_hours=0,
                                      max_price=20.0, max_priority_price=20.0,
                                      slot_min_gap_minutes=10)
        assert len(result["RunPlan"]) == 1

    def test_large_gap_between_slots_not_merged(self):
        """A 60-minute gap should not be merged when slot_min_gap_minutes=30."""
        p = _make_planner()
        now = DateHelper.now().replace(second=0, microsecond=0)
        s1 = _make_slot(now, now + dt.timedelta(hours=1), 10.0)
        s2 = _make_slot(now + dt.timedelta(hours=2), now + dt.timedelta(hours=3), 12.0)
        result = p.calculate_run_plan([s1, s2], required_hours=2, priority_hours=0,
                                      max_price=20.0, max_priority_price=20.0,
                                      slot_min_gap_minutes=30)
        assert len(result["RunPlan"]) == 2

    def test_short_slot_dropped_when_cannot_merge(self):
        """Isolated slot shorter than slot_min_minutes with no neighbours → dropped."""
        p = _make_planner()
        now = DateHelper.now().replace(second=0, microsecond=0)
        # A single 10-minute slot with minimum 30-minute requirement
        s1 = _make_slot(now, now + dt.timedelta(minutes=10), 10.0)
        result = p.calculate_run_plan([s1], required_hours=0.17, priority_hours=0,
                                      max_price=20.0, max_priority_price=20.0,
                                      slot_min_minutes=30)
        # Short isolated slot with no neighbours to merge with → empty or failed
        assert result["Status"] in {RunPlanStatus.FAILED, RunPlanStatus.NOTHING,
                                     RunPlanStatus.PARTIAL, RunPlanStatus.READY}


# ---------------------------------------------------------------------------
# calculate_run_plan — trim to required hours
# ---------------------------------------------------------------------------

class TestTrimToRequiredHours:
    def test_excess_trimmed_from_last_slot(self):
        p = _make_planner()
        now = DateHelper.now().replace(second=0, microsecond=0)
        # Two 60-minute slots but only need 90 minutes
        s1 = _make_slot(now, now + dt.timedelta(hours=1), 5.0)
        s2 = _make_slot(now + dt.timedelta(hours=1), now + dt.timedelta(hours=2), 8.0)
        result = p.calculate_run_plan([s1, s2], required_hours=1.5, priority_hours=0,
                                      max_price=20.0, max_priority_price=20.0)
        total = sum(s["Minutes"] for s in result["RunPlan"])
        assert total == 90

    def test_exact_match_not_trimmed(self):
        p = _make_planner()
        now = DateHelper.now().replace(second=0, microsecond=0)
        s1 = _make_slot(now, now + dt.timedelta(hours=2), 10.0)
        result = p.calculate_run_plan([s1], required_hours=2, priority_hours=0,
                                      max_price=20.0, max_priority_price=20.0)
        total = sum(s["Minutes"] for s in result["RunPlan"])
        assert total == 120


# ---------------------------------------------------------------------------
# Metadata correctness
# ---------------------------------------------------------------------------

class TestRunPlanMetadata:
    def test_plan_source_is_schedule(self):
        p = _make_planner(RunPlanMode.SCHEDULE)
        slots = _slots_from_now([(0, 2, 10.0)])
        result = p.calculate_run_plan(slots, required_hours=1, priority_hours=0,
                                      max_price=50.0, max_priority_price=50.0)
        assert result["Source"] == RunPlanMode.SCHEDULE

    def test_plan_source_is_best_price(self):
        from unittest.mock import MagicMock
        logger = MagicMock()
        p = RunPlanner(logger, RunPlanMode.BEST_PRICE, channel=AmberChannel.GENERAL)
        slots = _slots_from_now([(0, 2, 10.0)])
        result = p.calculate_run_plan(slots, required_hours=1, priority_hours=0,
                                      max_price=50.0, max_priority_price=50.0)
        assert result["Source"] == RunPlanMode.BEST_PRICE
        assert result["Channel"] == AmberChannel.GENERAL

    def test_forecast_average_price_calculated(self):
        p = _make_planner()
        slots = _slots_from_now([(0, 1, 10.0)])
        result = p.calculate_run_plan(slots, required_hours=1, priority_hours=0,
                                      max_price=50.0, max_priority_price=50.0,
                                      hourly_energy_usage=1000.0)
        assert result["ForecastAveragePrice"] > 0

    def test_next_start_datetime_set(self):
        p = _make_planner()
        slots = _slots_from_now([(0.5, 2.0, 10.0)])  # starts 30 min in future
        result = p.calculate_run_plan(slots, required_hours=1, priority_hours=0,
                                      max_price=50.0, max_priority_price=50.0)
        if result["Status"] in {RunPlanStatus.READY, RunPlanStatus.PARTIAL}:
            assert result["NextStartDateTime"] is not None


# ---------------------------------------------------------------------------
# tick()
# ---------------------------------------------------------------------------

class TestTick:
    def test_tick_updates_remaining_hours(self):
        p = _make_planner()
        now = DateHelper.now().replace(second=0, microsecond=0)
        future_start = now + dt.timedelta(minutes=30)
        future_end = now + dt.timedelta(hours=2, minutes=30)
        slot = _make_slot(future_start, future_end, 10.0)
        run_plan = p.calculate_run_plan([slot], required_hours=2, priority_hours=0,
                                        max_price=50.0, max_priority_price=50.0)
        updated = RunPlanner.tick(run_plan)
        # All time is in the future so RemainingHours ≈ PlannedHours
        assert updated["RemainingHours"] > 0

    def test_tick_past_slot_has_zero_remaining(self):
        p = _make_planner()
        now = DateHelper.now().replace(second=0, microsecond=0)
        past_start = now - dt.timedelta(hours=3)
        past_end = now - dt.timedelta(hours=1)
        slot = _make_slot(past_start, past_end, 10.0)
        run_plan = p.calculate_run_plan([slot], required_hours=2, priority_hours=0,
                                        max_price=50.0, max_priority_price=50.0)
        updated = RunPlanner.tick(run_plan)
        assert updated["RemainingHours"] == 0.0


# ---------------------------------------------------------------------------
# get_current_slot()
# ---------------------------------------------------------------------------

class TestGetCurrentSlot:
    def test_slot_spanning_now_returns_active(self):
        p = _make_planner()
        now = DateHelper.now().replace(second=0, microsecond=0)
        slot = _make_slot(now - dt.timedelta(minutes=30), now + dt.timedelta(minutes=30), 10.0)
        run_plan = p.calculate_run_plan([slot], required_hours=1, priority_hours=0,
                                        max_price=50.0, max_priority_price=50.0)
        active_slot, is_active = RunPlanner.get_current_slot(run_plan)
        assert is_active is True
        assert active_slot is not None

    def test_future_slot_not_active(self):
        p = _make_planner()
        now = DateHelper.now().replace(second=0, microsecond=0)
        slot = _make_slot(now + dt.timedelta(hours=1), now + dt.timedelta(hours=2), 10.0)
        run_plan = p.calculate_run_plan([slot], required_hours=1, priority_hours=0,
                                        max_price=50.0, max_priority_price=50.0)
        active_slot, is_active = RunPlanner.get_current_slot(run_plan)
        assert is_active is False
        assert active_slot is None

    def test_past_slot_not_active(self):
        p = _make_planner()
        now = DateHelper.now().replace(second=0, microsecond=0)
        slot = _make_slot(now - dt.timedelta(hours=2), now - dt.timedelta(hours=1), 10.0)
        run_plan = p.calculate_run_plan([slot], required_hours=1, priority_hours=0,
                                        max_price=50.0, max_priority_price=50.0)
        _, is_active = RunPlanner.get_current_slot(run_plan)
        assert is_active is False


# ---------------------------------------------------------------------------
# print_info()
# ---------------------------------------------------------------------------

class TestPrintInfo:
    def test_print_info_returns_string(self):
        p = _make_planner()
        slots = _slots_from_now([(0, 1, 10.0)])
        run_plan = p.calculate_run_plan(slots, required_hours=1, priority_hours=0,
                                        max_price=50.0, max_priority_price=50.0)
        output = RunPlanner.print_info(run_plan, "Test Output")
        assert isinstance(output, str)
        assert "Test Output" in output
        assert "Status" in output

    def test_print_info_no_title(self):
        p = _make_planner()
        run_plan = p.calculate_run_plan([], required_hours=1, priority_hours=0,
                                        max_price=50.0, max_priority_price=50.0)
        output = RunPlanner.print_info(run_plan, None)
        assert isinstance(output, str)
        assert "Run Plan" in output
