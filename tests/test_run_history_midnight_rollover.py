# ruff: noqa: I001
import datetime as dt

import pytest
import run_history
from local_enumerations import OutputStatusData
from org_enums import StateReasonOff, StateReasonOn, SystemState


class FakeLogger:
    def __init__(self):
        self.events: list[tuple] = []

    def log_message(self, msg: str, level: str = "info"):
        self.events.append(("log", level, msg))

    def send_email(self, subject: str, body: str):
        self.events.append(("email", subject, body))


def test_meter_run_is_split_across_midnight(monkeypatch: pytest.MonkeyPatch):
    local_tz = dt.datetime.now().astimezone().tzinfo

    times = {
        "init": dt.datetime(2026, 1, 19, 23, 50, tzinfo=local_tz),
        "start": dt.datetime(2026, 1, 19, 23, 0, tzinfo=local_tz),
        "last_tick": dt.datetime(2026, 1, 19, 23, 59, tzinfo=local_tz),
        "tick": dt.datetime(2026, 1, 20, 0, 1, tzinfo=local_tz),
    }
    clock = {"now": times["init"]}

    def _now() -> dt.datetime:
        return clock["now"]

    def _today() -> dt.date:
        return clock["now"].date()

    monkeypatch.setattr(run_history.DateHelper, "now", staticmethod(_now))
    monkeypatch.setattr(run_history.DateHelper, "today", staticmethod(_today))

    logger = FakeLogger()
    output_config = {
        "Name": "Test Meter",
        "TargetHours": 1,
        "DaysOfHistory": 7,
        "MaxShortfallHours": 0,
        "MinEnergyToLog": 0,
    }

    rh = run_history.RunHistory(logger=logger, output_config=output_config)  # pyright: ignore[reportArgumentType]

    def make_status(meter_reading: float, *, is_on: bool = True) -> OutputStatusData:
        return OutputStatusData(
            meter_reading=meter_reading,
            power_draw=0.0,
            is_on=is_on,
            target_hours=1.0,
            current_price=20.0,
            output_type="meter",
        )

    rh.start_run(SystemState.AUTO, StateReasonOn.ACTIVE_RUN_PLAN, make_status(1000.0), start_time=times["start"])
    rh.last_tick = times["last_tick"]

    clock["now"] = times["tick"]
    have_rolled = rh.tick(make_status(1010.0))
    assert have_rolled is True

    assert len(rh.history["DailyData"]) >= 2
    yesterday = rh.history["DailyData"][-2]
    today = rh.history["DailyData"][-1]

    assert yesterday["Date"] == dt.date(2026, 1, 19)
    assert today["Date"] == dt.date(2026, 1, 20)

    # Yesterday's open run should be closed at day end.
    yesterday_run = yesterday["DeviceRuns"][-1]
    assert yesterday_run["ReasonStopped"] == StateReasonOff.DAY_END
    assert yesterday_run["EndTime"] == dt.datetime(2026, 1, 19, 23, 59, 59, tzinfo=local_tz)

    # Today's run should be created at midnight with DAY_START.
    assert today["DeviceRuns"], "Expected a new run to be created for the new day"
    today_run = today["DeviceRuns"][0]
    assert today_run["ReasonStarted"] == StateReasonOn.DAY_START
    assert today_run["StartTime"] == dt.datetime(2026, 1, 20, 0, 0, 0, tzinfo=local_tz)
    assert today_run["EndTime"] is None

    # Boundary reading should be pro-rated: half of the 10 unit delta across the 2 minute window.
    assert today_run["MeterReadAtStart"] == pytest.approx(1005.0)
    assert yesterday_run["PriorMeterRead"] == pytest.approx(1005.0)
    assert yesterday_run["EnergyUsed"] == pytest.approx(5.0)
