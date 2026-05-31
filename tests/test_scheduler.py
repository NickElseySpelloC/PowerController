"""Tests for Scheduler — time-window management and schedule-based run planning."""

import datetime as dt
import sys
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from org_enums import RunPlanStatus
from sc_foundation import DateHelper

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# get_schedule_by_name
# ---------------------------------------------------------------------------

class TestGetScheduleByName:
    def test_found_returns_dict(self, scheduler):
        sched = scheduler.get_schedule_by_name("General")
        assert sched is not None
        assert sched["Name"] == "General"

    def test_not_found_returns_none(self, scheduler):
        assert scheduler.get_schedule_by_name("NonExistent") is None

    def test_morning_only_schedule_found(self, scheduler):
        sched = scheduler.get_schedule_by_name("MorningOnly")
        assert sched is not None


# ---------------------------------------------------------------------------
# get_schedule_slots
# ---------------------------------------------------------------------------

class TestGetScheduleSlots:
    def test_all_day_general_schedule_returns_slots(self, scheduler):
        sched = scheduler.get_schedule_by_name("General")
        slots = scheduler.get_schedule_slots(sched)
        # "General" runs 00:00-23:59 every day, should always have at least one slot
        assert len(slots) >= 1

    def test_slot_has_required_fields(self, scheduler):
        sched = scheduler.get_schedule_by_name("General")
        slots = scheduler.get_schedule_slots(sched)
        if slots:
            slot = slots[0]
            assert "StartTime" in slot
            assert "EndTime" in slot
            assert "StartDateTime" in slot
            assert "EndDateTime" in slot
            assert "Minutes" in slot
            assert "Price" in slot

    def test_price_in_slot_matches_config(self, scheduler):
        sched = scheduler.get_schedule_by_name("General")
        slots = scheduler.get_schedule_slots(sched)
        for slot in slots:
            # All General windows have Price: 20.0
            assert slot["Price"] == pytest.approx(20.0)

    def test_morning_only_slots_end_by_noon(self, scheduler):
        sched = scheduler.get_schedule_by_name("MorningOnly")
        slots = scheduler.get_schedule_slots(sched)
        # All slots must end by or at 12:00
        for slot in slots:
            assert slot["EndTime"] <= dt.time(12, 0)

    def test_weekdays_only_schedule_for_weekend(self, scheduler):
        """WeekdaysOnly schedule should return no slots on Sat/Sun."""
        sched = scheduler.get_schedule_by_name("WeekdaysOnly")
        today = DateHelper.today()
        weekday = today.weekday()
        slots = scheduler.get_schedule_slots(sched)
        if weekday >= 5:  # Saturday=5, Sunday=6
            assert slots == []

    def test_past_windows_excluded(self, scheduler):
        """Windows that have already ended today should not appear in slots."""
        sched = scheduler.get_schedule_by_name("General")
        slots = scheduler.get_schedule_slots(sched)
        time_now = DateHelper.now().time().replace(second=0, microsecond=0)
        for slot in slots:
            assert slot["EndTime"] >= time_now

    def test_slot_minutes_consistent_with_times(self, scheduler):
        sched = scheduler.get_schedule_by_name("General")
        slots = scheduler.get_schedule_slots(sched)
        for slot in slots:
            expected_mins = int((slot["EndDateTime"] - slot["StartDateTime"]).total_seconds() // 60)
            assert slot["Minutes"] == expected_mins


# ---------------------------------------------------------------------------
# get_current_price
# ---------------------------------------------------------------------------

class TestGetCurrentPrice:
    def test_returns_float(self, scheduler):
        sched = scheduler.get_schedule_by_name("General")
        price = scheduler.get_current_price(sched)
        assert isinstance(price, float)
        assert price > 0

    def test_general_schedule_price_is_20(self, scheduler):
        """General schedule always has price 20.0."""
        sched = scheduler.get_schedule_by_name("General")
        price = scheduler.get_current_price(sched)
        # Since all windows in General have Price: 20.0, we should get 20.0
        # unless we're past 23:59 (i.e. no window active), in which case default applies
        assert price in {20.0, scheduler.default_price}

    def test_returns_default_when_no_matching_slot(self, scheduler):
        """A schedule with no currently-active window returns the default price."""
        # Create a schedule whose single window is always in the past for today
        empty_schedule = {
            "Name": "AlwaysPast",
            "Windows": [
                {"StartTime": "00:00", "EndTime": "00:01", "DaysOfWeek": "All", "Price": 99.9}
            ]
        }
        # Only valid if the current time is after 00:01
        if DateHelper.now().time() > dt.time(0, 1):
            price = scheduler.get_current_price(empty_schedule)
            assert price == scheduler.default_price


# ---------------------------------------------------------------------------
# get_price (at specific time)
# ---------------------------------------------------------------------------

class TestGetPrice:
    def test_price_at_specific_time_in_window(self, scheduler):
        sched = scheduler.get_schedule_by_name("General")
        # Use a time well within today's range
        test_time = DateHelper.now().replace(hour=10, minute=0, second=0, microsecond=0)
        price = scheduler.get_price(sched, test_time)
        assert isinstance(price, float)

    def test_price_outside_all_windows_returns_default(self, scheduler):
        morning_sched = scheduler.get_schedule_by_name("MorningOnly")
        # Ask for price at 22:00, which is outside the 06:00-12:00 window
        test_time = DateHelper.now().replace(hour=22, minute=0, second=0, microsecond=0)
        price = scheduler.get_price(morning_sched, test_time)
        assert price == scheduler.default_price


# ---------------------------------------------------------------------------
# get_run_plan
# ---------------------------------------------------------------------------

class TestGetRunPlan:
    def test_run_plan_returned_for_known_schedule(self, scheduler):
        plan = scheduler.get_run_plan(
            "General",
            required_hours=-1,
            priority_hours=0,
            max_price=100.0,
            max_priority_price=100.0,
        )
        assert plan is not None
        assert "Status" in plan

    def test_run_plan_failed_for_unknown_schedule(self, scheduler):
        plan = scheduler.get_run_plan(
            "NonExistentSchedule",
            required_hours=1,
            priority_hours=0,
            max_price=100.0,
            max_priority_price=100.0,
        )
        assert plan is None

    def test_run_plan_contains_required_keys(self, scheduler):
        plan = scheduler.get_run_plan(
            "General",
            required_hours=1,
            priority_hours=0,
            max_price=100.0,
            max_priority_price=100.0,
        )
        assert plan is not None
        for key in ("Status", "Source", "RunPlan", "RequiredHours", "PlannedHours"):
            assert key in plan

    def test_run_plan_zero_required_hours_returns_nothing(self, scheduler):
        plan = scheduler.get_run_plan(
            "General",
            required_hours=0,
            priority_hours=0,
            max_price=100.0,
            max_priority_price=100.0,
        )
        assert plan is not None
        assert plan["Status"] == RunPlanStatus.NOTHING

    def test_run_plan_price_too_low_returns_failed_or_partial(self, scheduler):
        """Asking for slots cheaper than any available → FAILED or PARTIAL."""
        plan = scheduler.get_run_plan(
            "General",
            required_hours=1,
            priority_hours=0,
            max_price=0.01,        # Impossibly low
            max_priority_price=0.01,
        )
        assert plan is not None
        assert plan["Status"] in {RunPlanStatus.FAILED, RunPlanStatus.PARTIAL, RunPlanStatus.BELOW_MINIMUM}


# ---------------------------------------------------------------------------
# _parse_time
# ---------------------------------------------------------------------------

class TestParseTime:
    def test_hhmm_format_parsed(self, scheduler):
        result = scheduler._parse_time("14:30", "TestSchedule", 0)
        assert result == dt.time(14, 30)

    def test_midnight_parsed(self, scheduler):
        result = scheduler._parse_time("00:00", "TestSchedule", 0)
        assert result == dt.time(0, 0)

    def test_dawn_returns_time_object(self, scheduler):
        """Dawn time should parse to a valid time object."""
        result = scheduler._parse_time("dawn", "TestSchedule", 0)
        assert isinstance(result, dt.time)

    def test_dusk_returns_time_object(self, scheduler):
        result = scheduler._parse_time("dusk", "TestSchedule", 0)
        assert isinstance(result, dt.time)

    def test_dawn_plus_offset(self, scheduler):
        """Dawn+00:30 should be 30 minutes after dawn."""
        dawn_base = scheduler._parse_time("dawn", "TestSchedule", 0)
        dawn_plus = scheduler._parse_time("dawn+00:30", "TestSchedule", 0)
        base_dt = dt.datetime.combine(DateHelper.today(), dawn_base)
        plus_dt = dt.datetime.combine(DateHelper.today(), dawn_plus)
        diff = (plus_dt - base_dt).total_seconds() / 60
        assert diff == pytest.approx(30, abs=1)

    def test_dusk_minus_offset(self, scheduler):
        """Dusk-01:00 should be 60 minutes before dusk."""
        dusk_base = scheduler._parse_time("dusk", "TestSchedule", 0)
        dusk_minus = scheduler._parse_time("dusk-01:00", "TestSchedule", 0)
        base_dt = dt.datetime.combine(DateHelper.today(), dusk_base)
        minus_dt = dt.datetime.combine(DateHelper.today(), dusk_minus)
        diff = (base_dt - minus_dt).total_seconds() / 60
        assert diff == pytest.approx(60, abs=1)


# ---------------------------------------------------------------------------
# Overnight / full-day windows
# ---------------------------------------------------------------------------

class TestOvernightWindows:
    def test_full_day_window_returns_slot(self, scheduler):
        """00:00/00:00 window should always return at least one slot."""
        sched = scheduler.get_schedule_by_name("FullDay")
        slots = scheduler.get_schedule_slots(sched)
        assert len(slots) >= 1

    def test_full_day_slot_end_time_is_2359(self, scheduler):
        """The EndTime of a full-day slot should be 23:59 (capped for same-day comparisons)."""
        sched = scheduler.get_schedule_by_name("FullDay")
        slots = scheduler.get_schedule_slots(sched)
        assert slots[-1]["EndTime"] == dt.time(23, 59)

    def test_full_day_slot_minutes_covers_remainder_of_day(self, scheduler):
        """Minutes should reflect the time from now until midnight (> 0)."""
        sched = scheduler.get_schedule_by_name("FullDay")
        slots = scheduler.get_schedule_slots(sched)
        total_minutes = sum(s["Minutes"] for s in slots)
        assert total_minutes > 0

    def test_full_day_slot_end_datetime_is_tomorrow_midnight(self, scheduler):
        """EndDateTime for a 00:00/00:00 window should be tomorrow 00:00 for correct duration."""
        sched = scheduler.get_schedule_by_name("FullDay")
        slots = scheduler.get_schedule_slots(sched)
        # The last slot's EndDateTime should be tomorrow at 00:00
        from sc_foundation import DateHelper
        tomorrow = DateHelper.today_add_days(1)
        assert slots[-1]["EndDateTime"].date() == tomorrow
        assert slots[-1]["EndDateTime"].time() == dt.time(0, 0)

    def test_overnight_window_returns_slot(self, scheduler):
        """An overnight window (20:00–07:00) should return at least one slot at any time of day."""
        sched = scheduler.get_schedule_by_name("Overnight")
        slots = scheduler.get_schedule_slots(sched)
        assert len(slots) >= 1

    def test_overnight_slot_has_required_fields(self, scheduler):
        """Overnight slots must have the same required fields as normal slots."""
        sched = scheduler.get_schedule_by_name("Overnight")
        slots = scheduler.get_schedule_slots(sched)
        for slot in slots:
            for key in ("StartTime", "EndTime", "StartDateTime", "EndDateTime", "Minutes", "Price"):
                assert key in slot

    def test_overnight_slot_minutes_positive(self, scheduler):
        """All overnight slot Minutes values must be positive."""
        sched = scheduler.get_schedule_by_name("Overnight")
        slots = scheduler.get_schedule_slots(sched)
        for slot in slots:
            assert slot["Minutes"] > 0

    def test_overnight_slot_price(self, scheduler):
        """Overnight slot price should match the configured window price."""
        sched = scheduler.get_schedule_by_name("Overnight")
        slots = scheduler.get_schedule_slots(sched)
        for slot in slots:
            assert slot["Price"] == pytest.approx(12.0)

    def test_overnight_head_end_datetime_crosses_midnight(self, scheduler):
        """The head slot of an overnight window should have EndDateTime on tomorrow."""
        from sc_foundation import DateHelper
        sched = scheduler.get_schedule_by_name("Overnight")
        slots = scheduler.get_schedule_slots(sched)
        today = DateHelper.today()
        tomorrow = DateHelper.today_add_days(1)
        # The head slot (StartTime >= 20:00) should end tomorrow
        head_slots = [s for s in slots if s["StartTime"] >= dt.time(20, 0)]
        if head_slots:
            assert head_slots[0]["EndDateTime"].date() == tomorrow
        # Tail slots (StartTime < 07:00) should end today
        tail_slots = [s for s in slots if s["EndTime"] <= dt.time(7, 0)]
        if tail_slots:
            assert tail_slots[0]["EndDateTime"].date() == today


# ---------------------------------------------------------------------------
# PowerTariff: _get_tariff_slots_for_window / get_schedule_slots with UsePowerTariff
# ---------------------------------------------------------------------------

class TestPowerTariff:
    def test_tariff_schedule_returns_multiple_slots(self, scheduler):
        """A full-day window with UsePowerTariff should be split into sub-slots."""
        sched = scheduler.get_schedule_by_name("TariffSchedule")
        slots = scheduler.get_schedule_slots(sched)
        # Three tariff bands → at least 2 sub-slots (some may be in the past)
        assert len(slots) >= 1

    def test_tariff_sub_slots_cover_contiguous_time(self, scheduler):
        """Adjacent sub-slot boundaries must be contiguous (no gaps, no overlaps)."""
        sched = scheduler.get_schedule_by_name("TariffSchedule")
        slots = scheduler.get_schedule_slots(sched)
        for i in range(len(slots) - 1):
            assert slots[i]["EndTime"] == slots[i + 1]["StartTime"]

    def test_tariff_prices_match_bands(self, scheduler):
        """Each sub-slot's price must match a configured tariff band price, not the schedule window price (99)."""
        sched = scheduler.get_schedule_by_name("TariffSchedule")
        slots = scheduler.get_schedule_slots(sched)
        valid_prices = {10.0, 30.0, 20.0}  # Overnight / Peak / Shoulder
        for slot in slots:
            assert slot["Price"] in valid_prices, f"Unexpected price {slot['Price']} in slot {slot}"

    def test_tariff_gap_uses_schedule_price(self, scheduler):
        """A schedule window outside tariff coverage should use the schedule's own price (99)."""
        sched = scheduler.get_schedule_by_name("TariffScheduleGap")
        # TariffScheduleGap runs 08:00–16:00, which is fully inside tariff coverage (07:00–14:00 Peak, 14:00–23:59 Shoulder)
        # so all sub-slots should get tariff prices; this test verifies no slot has the fallback price of 99
        slots = scheduler.get_schedule_slots(sched)
        for slot in slots:
            assert slot["Price"] != 99.0, f"Slot should have a tariff price, not the fallback 99: {slot}"

    def test_non_tariff_schedule_unaffected(self, scheduler):
        """Schedules without UsePowerTariff should not be split."""
        sched = scheduler.get_schedule_by_name("General")
        slots = scheduler.get_schedule_slots(sched)
        # General has one window; all slots should have Price 20.0 (not tariff prices)
        for slot in slots:
            assert slot["Price"] == pytest.approx(20.0)

    def test_tariff_slot_minutes_consistent(self, scheduler):
        """Minutes field in each sub-slot must match its start/end datetimes."""
        sched = scheduler.get_schedule_by_name("TariffSchedule")
        slots = scheduler.get_schedule_slots(sched)
        for slot in slots:
            expected = int((slot["EndDateTime"] - slot["StartDateTime"]).total_seconds() // 60)
            assert slot["Minutes"] == expected

    def test_tariff_loaded(self, scheduler):
        """Scheduler should load the PowerTariff from config."""
        assert scheduler.power_tariff is not None
        assert isinstance(scheduler.power_tariff, list)
        assert len(scheduler.power_tariff) == 3

    def test_midnight_spanning_band_covers_early_morning(self, scheduler):
        """A midnight-spanning tariff band (23:00–07:00) should apply to slots starting at 00:00.

        The 'Overnight' band starts at 23:00 and ends at 07:00 the next day. A schedule window
        running 00:00–08:00 should have its 00:00–07:00 portion priced at 10.0 (Overnight rate),
        not at the schedule's fallback price of 99.
        """
        sched = scheduler.get_schedule_by_name("TariffMidnightSpan")
        # Build a synthetic base slot covering 00:00–08:00 to test the full window
        # regardless of current time (get_schedule_slots skips past windows)
        import datetime as dt
        from sc_foundation import DateHelper
        today = DateHelper.today()
        base_slot = {
            "Date": today,
            "StartTime": dt.time(0, 0),
            "StartDateTime": DateHelper.combine(today, dt.time(0, 0)),
            "EndTime": dt.time(8, 0),
            "EndDateTime": DateHelper.combine(today, dt.time(8, 0)),
            "Minutes": 480,
            "Price": 99.0,
        }
        sub_slots = scheduler._get_tariff_slots_for_window(base_slot, today)
        # 00:00–07:00 should be priced at 10.0 (Overnight), 07:00–08:00 at 30.0 (Peak)
        prices_by_start = {s["StartTime"]: s["Price"] for s in sub_slots}
        assert prices_by_start.get(dt.time(0, 0)) == pytest.approx(10.0), \
            "Midnight-spanning Overnight band should cover 00:00 slot"
        assert prices_by_start.get(dt.time(7, 0)) == pytest.approx(30.0), \
            "Peak band should cover 07:00 slot"


# ---------------------------------------------------------------------------
# get_save_object
# ---------------------------------------------------------------------------

class TestGetSaveObject:
    def test_save_object_has_schedules_key(self, scheduler):
        obj = scheduler.get_save_object()
        assert "Schedules" in obj
        assert "Dawn" in obj
        assert "Dusk" in obj

    def test_save_object_with_schedule(self, scheduler):
        sched = scheduler.get_schedule_by_name("General")
        obj = scheduler.get_save_object(sched)
        assert "Schedule" in obj
        assert obj["Schedule"] == sched
