"""RunHistory class is used to manage the history of executed run plans."""

import datetime as dt

from sc_utility import DateHelper, SCLogger


class RunHistory:
    def __init__(self, logger: SCLogger):
        self.logger = logger
        self.history = []

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
    def _create_run_object(start_time: dt.datetime | None, meter_reading: float | None):
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
            "StartTime": start_time,
            "EndTime": None,
            "ActualHours": 0.0,
            "MeterReadAtStart": meter_reading,
            "EnergyUsedForRun": None,
            "AveragePrice": 0.0,
            "TotalCost": 0.0
        }
        return new_run
