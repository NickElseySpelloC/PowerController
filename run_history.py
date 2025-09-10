"""RunHistory class is used to manage the history of executed run plans."""

import datetime as dt

from sc_utility import DateHelper, SCLogger

from enumerations import (
    StateReasonOff,
    StateReasonOn,
    SystemState,
)


class RunHistory:
    """Manages the history of executed run plans for an output device."""
    def __init__(self, logger: SCLogger, history: dict | None = None):
        """Initializes the RunHistory.

        Args:
            logger (SCLogger): The logger for the system.
            history (list | None): The initial history data read from file. If None, an empty history is created.
        """
        self.logger = logger
        self.last_tick = DateHelper.now()
        if history is None:
            self.history = self._create_history_object()
        else:
            self.history = history

    @staticmethod
    def _create_history_object() -> dict:
        """Return a new empty history object. This is the parent object holding data for all days and the summaries."""
        new_history = {
            "LastUpdate": DateHelper.now(),   # When was this object last updated?
            "TotalHours": 0.0,  # Total hours across the entire history
            "HistoryDays": 0,  # How many days of history so we have = len(self['DailyData'])
            "LastStartTime": None,   # StartTime of the most recent event
            "LastMeterReadAtStart": None,  # MeterReadAtStart of the most recent event
            "CurrentTotals": {    # Totals for all the days in the current history
                "EnergyUsed": 0.0,
                "TotalCost": 0.0,
                "AveragePrice": 0.0,
                "ActualHours": 0.0
            },
            "EarlierTotals": {   # Totals for all the days prior to the current history that have rolled off
                "EnergyUsed": 0.0,
                "TotalCost": 0.0,
                "AveragePrice": 0.0,
                "ActualHours": 0.0
            },
            "AlltimeTotals": {   # Sum of CurrentTotals and EarlierTotals
                "EnergyUsed": 0.0,
                "TotalCost": 0.0,
                "AveragePrice": 0.0,
                "ActualHours": 0.0
            },
            "DailyData": []  # List of day objects as created by _create_day_object
        }
        return new_history

    @staticmethod
    def _create_day_object(obj_date: dt.date):
        """Create the object that represents a single day of date within the run history.

        Args:
            obj_date (dt.date): The date for the history day object.

        Returns:
            dict: The created history day object.
        """
        new_day = {
            "Date": obj_date,
            "PriorShortfall": 0.0,  # Total shortfall hours carried over from prior days
            "TargetHours": 0.0,  # Total hours targeted to run on this day as at the start of the day (inc. shortfall)
            "ActualHours": 0.0,  # Total hours actually run on this day
            "RemainingHours": 0.0,  # Total hours remaining to run on this day
            "EnergyUsed": 0.0,   # Energy used (in Wh) on this day
            "AveragePrice": 0.0,  # Average price paid in c/kWh for the energy on this day
            "TotalCost": 0.0,  # Total cost incurred for the energy used on this day in cents
            "DeviceRuns": []  # The individual run instances for this day
        }
        return new_day

    @staticmethod
    def _create_run_object(start_time: dt.datetime | None = None, meter_reading: float | None = None) -> dict:
        """Create the object that represents a single run instance within the run history.

        Args:
            start_time (dt.datetime | None): The start time of the run.
            meter_reading (float | None): The meter reading at the start of the run.

        Returns:
            dict: The created run object.
        """
        if start_time is None:
            start_time = DateHelper.now()

        new_run = {
            "SystemState": None,       # SystemState enum value when the run started
            "ReasonStarted": None,    # StateReasonOn enum value why the output was turned on
            "ReasonStopped": None,    # StateReasonOff enum value why the output was turned
            "StartTime": start_time,    # Datetime object, not just time
            "EndTime": None,            # Datetime object, not just time
            "ActualHours": 0.0,
            "MeterReadAtStart": meter_reading,
            "EnergyUsedForRun": None,
            "AveragePrice": 0.0,
            "TotalCost": 0.0
        }
        return new_run

    def tick(self):
        """Perform periodic updates to the run history."""
        if self._have_rolled_over_to_new_day():
            # Handle removal of oldest day if beyond threshold
            oldest_day = self.history["DailyData"][0]
            if self.history["HistoryDays"] > 7:  # Assuming we keep a maximum of 7 days of history
                self.history["DailyData"].pop(0)
                # Carry forward shortfall to new oldest day
                if self.history["DailyData"]:
                    self.history["DailyData"][0]["PriorShortfall"] += oldest_day["RemainingHours"]

            # If the last run for the most recent day is still open, create a new entry for today
            last_day = self.history["DailyData"][-1]
            if last_day["DeviceRuns"] and last_day["DeviceRuns"][-1]["EndTime"] is None:
                last_run = last_day["DeviceRuns"][-1]
                # Set the EndTime for the last run of the previous day
                last_run["EndTime"] = dt.datetime.combine(last_day["Date"], dt.time(23, 59, 59))
                last_run["ActualHours"] = (last_run["EndTime"] - last_run["StartTime"]).total_seconds() / 3600.0

                # Now create a new run entry for today, carrying over the status
                new_day = self._create_day_object(DateHelper.now().date())
                new_run = self._create_run_object(dt.datetime.combine(new_day["Date"], dt.time(0, 0, 0)), last_run["MeterReadAtStart"])
                new_run["SystemState"] = last_run["SystemState"]
                new_run["ReasonStarted"] = last_run["ReasonStarted"]
                new_day["DeviceRuns"].append(new_run)
                self.history["DailyData"].append(new_day)

        self.update_totals()
        self.last_tick = DateHelper.now()

    def _have_rolled_over_to_new_day(self) -> bool:
        """Check if the current date has rolled over to a new day compared to the last update.

        Returns:
            bool: True if a new day has started, False otherwise.
        """
        if not self.history["DailyData"]:
            return False
        last_date = self.history["DailyData"][-1]["Date"]
        current_date = DateHelper.now().date()
        return current_date > last_date

    def get_current_run(self) -> dict | None:
        """Get the current active run if there is one.

        Returns:
            dict | None: The current active run object or None if there is no active run.
        """
        if not self.history["DailyData"]:
            return None
        last_day = self.history["DailyData"][-1]
        if not last_day["DeviceRuns"]:
            return None
        last_run = last_day["DeviceRuns"][-1]
        if last_run["EndTime"] is None:
            return last_run
        return None

    def start_run(self, new_system_state: SystemState, reason: StateReasonOn):
        """Add a new run instance to the history.

        Args:
            new_system_state (SystemState): The system state when the run started.
            reason (StateReasonOn): The reason why the output was turned on.
        """
        # First call tick() if we haven't done so in the 10 seconds
        if (DateHelper.now() - self.last_tick).total_seconds() > 10:
            self.tick()

        current_run = self.get_current_run()
        if current_run is not None and not current_run["EndTime"]:
            if current_run["SystemState"] == new_system_state and current_run["ReasonStarted"] == reason:
                # Already running with the same state and reason, no action needed
                return
            # Stop the current run before starting a new one
            self.stop_run(StateReasonOff.STATUS_CHANGE, None)

        new_run = self._create_run_object()
        new_run["SystemState"] = new_system_state
        new_run["ReasonStarted"] = reason

        # Find or create today's day object and append the new run
        today = DateHelper.today()
        if self.history["DailyData"] and self.history["DailyData"][-1]["Date"] == today:
            day_obj = self.history["DailyData"][-1]
        else:
            day_obj = self._create_day_object(today)
            self.history["DailyData"].append(day_obj)
        day_obj["DeviceRuns"].append(new_run)

        self.update_totals()

    def stop_run(self, reason: StateReasonOff, meter_reading: float | None):
        """Stop the current active run and update its details.

        Args:
            reason (StateReasonOff): The reason why the output was turned off.
            meter_reading (float | None): The meter reading at the end of the run.
        """
        # First call tick() if we haven't done so in the 10 seconds
        if (DateHelper.now() - self.last_tick).total_seconds() > 10:
            self.tick()

        current_run = self.get_current_run()
        if current_run is None:
            # No active run to stop
            return

        current_run["EndTime"] = DateHelper.now()
        current_run["ActualHours"] = (current_run["EndTime"] - current_run["StartTime"]).total_seconds() / 3600.0
        current_run["ReasonStopped"] = reason

        self.update_totals()

    def update_totals(self):
        """Update all the running totals in the history object."""
        """TO DO: 
        - Implement the logic to update totals based on the run history
        - Cap maximum shortfall
        """
