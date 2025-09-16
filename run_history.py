"""RunHistory class is used to manage the history of executed run plans."""

import datetime as dt

from sc_utility import DateHelper, SCLogger

from enumerations import (
    OutputStatusData,
    RunPlanTargetHours,
    StateReasonOff,
    StateReasonOn,
    SystemState,
)


class RunHistory:
    """Manages the history of executed run plans for an output device."""
    def __init__(self, logger: SCLogger, output_config: dict, saved_history: dict | None = None):
        """Initializes the RunHistory.

        Args:
            logger (SCLogger): The logger for the system.
            output_config (dict): The configuration for the output device.
            saved_history (dict | None): The history object deserialized from json data, used to initialise the RunHistory. If None, an empty history is created.
        """
        self.logger = logger
        self.output_config = output_config
        self.last_tick = DateHelper.now()
        self.run_plan_target_mode = RunPlanTargetHours.ALL_HOURS if output_config.get("TargetHours") == -1 else RunPlanTargetHours.NORMAL
        self.output_name = output_config.get("Name") or "Unknown"
        self.dates_off = []
        self.history: dict
        if saved_history is None:
            self.history = self._create_history_object()
        else:
            self.history = saved_history

        # Now set the min / max / target hours. May throw runtime error
        self.initialise(output_config)

        # Now do a tick just to make sure everything is in order
        status_data = OutputStatusData(meter_reading=0.0, target_hours=None, current_price=15.0)
        self.tick(status_data)

    def initialise(self, output_config: dict):
        """Initialise or reinitialise the configured values for this object.

        Args:
            target_hours (float | None): The target hours for the run plan.
            output_config (dict): The configuration for the output device.
        """
        self.output_config = output_config
        self.run_plan_target_mode = RunPlanTargetHours.ALL_HOURS if output_config.get("TargetHours") == -1 else RunPlanTargetHours.NORMAL
        self.output_name = output_config.get("Name") or "Unknown"
        self.max_shortfall_hours = output_config.get("MaxShortfallHours", 12)
        self.max_history_days = output_config.get("DaysOfHistory", 7)

    @staticmethod
    def _create_history_object() -> dict:
        """Return a new empty history object. This is the parent object holding data for all days and the summaries."""
        new_history = {
            "LastUpdate": DateHelper.now(),   # When was this object last updated?
            "HistoryDays": 0,  # How many days of history so we have = len(self['DailyData'])
            "LastStartTime": None,   # StartTime of the most recent event if event is open
            "LastMeterRead": 0,  # Most recently available meter read
            "CurrentPrice": 0.0,  # Most recently available current price
            "CurrentTotals": {    # Totals for all the days in the current history
                "EnergyUsed": 0,  # Energy used (in Wh)
                "HourlyEnergyUsed": 0.0,  # Average energy used per hour in Wh
                "TotalCost": 0.0,  # Total cost in $
                "AveragePrice": 0.0,  # Average price in c/kWh
                "ActualHours": 0.0
            },
            "EarlierTotals": {   # Totals for all the days prior to the current history that have rolled off
                "EnergyUsed": 0,
                "HourlyEnergyUsed": 0.0,  # Average energy used per hour in Wh
                "TotalCost": 0.0,
                "AveragePrice": 0.0,
                "ActualHours": 0.0
            },
            "AlltimeTotals": {   # Sum of CurrentTotals and EarlierTotals
                "EnergyUsed": 0,
                "HourlyEnergyUsed": 0.0,  # Average energy used per hour in Wh
                "TotalCost": 0.0,
                "AveragePrice": 0.0,
                "ActualHours": 0.0
            },
            "DailyData": []  # List of day objects as created by _create_day_object
        }
        return new_history

    @staticmethod
    def _create_day_object(obj_date: dt.date, status_data: OutputStatusData):
        """Create the object that represents a single day of date within the run history.

        Args:
            obj_date (dt.date): The date for the history day object.
            status_data (OutputStatusData): The status data for the associated output.

        Returns:
            dict: The created history day object.
        """
        new_day = {
            "Date": obj_date,
            "TargetHours": status_data.target_hours,
            "PriorShortfall": 0.0,  # Total shortfall hours carried over from prior days
            "ActualHours": 0.0,  # Total hours actually run on this day
            "EnergyUsed": 0,   # Energy used (in Wh) on this day
            "HourlyEnergyUsed": 0.0,  # Average energy used per hour in Wh
            "TotalCost": 0.0,  # Total cost incurred for the energy used on this day in $
            "AveragePrice": 0.0,  # Average price paid in c/kWh for the energy on this day
            "DeviceRuns": []  # The individual run instances for this day
        }
        return new_day

    @staticmethod
    def _create_run_object(start_time: dt.datetime, status_data: OutputStatusData) -> dict:
        """Create the object that represents a single run instance within the run history.

        Args:
            start_time (dt.datetime | None): The start time of the run.
            status_data (OutputStatusData): The status data for the associated output.

        Returns:
            dict: The created run object.
        """
        new_run = {
            "SystemState": None,       # SystemState enum value when the run started
            "ReasonStarted": None,    # StateReasonOn enum value why the output was turned on
            "ReasonStopped": None,    # StateReasonOff enum value why the output was turned
            "StartTime": start_time,    # Datetime object, not just time
            "EndTime": None,            # Datetime object, not just time
            "ActualHours": 0.0,
            "MeterReadAtStart": status_data.meter_reading,
            "PriorMeterRead": status_data.meter_reading,     # This should only be changed by _calculate_values_for_open_run()
            "LastActualPrice": 0.0,
            "EnergyUsed": 0,        # Energy used (in Wh)
            "TotalCost": 0.0,       # Total cost in $
            "AveragePrice": 0.0,    # Average price in c/kWh
        }
        return new_run

    def tick(self, status_data: OutputStatusData):
        """Perform periodic updates to the run history."""
        if self._have_rolled_over_to_new_day():
            # Handle removal of oldest day if beyond threshold
            oldest_day = self.history["DailyData"][0]
            if self.history["HistoryDays"] > self.max_history_days:
                # Add totals for rolling off days to EarlierTotals
                self.history["EarlierTotals"]["EnergyUsed"] += oldest_day["EnergyUsed"]
                self.history["EarlierTotals"]["TotalCost"] += oldest_day["TotalCost"]
                self.history["EarlierTotals"]["ActualHours"] += oldest_day["ActualHours"]
                self.history["EarlierTotals"]["AveragePrice"] = self.history["EarlierTotals"]["TotalCost"] / (self.history["EarlierTotals"]["EnergyUsed"] / 1000) if self.history["EarlierTotals"]["EnergyUsed"] > 0 else 0

                # Now remove the oldest day
                self.history["DailyData"].pop(0)

            # If the last run for the most recent day is still open, create a new entry for today
            if self.history["DailyData"]:
                last_day = self.history["DailyData"][-1]
                if last_day["DeviceRuns"] and last_day["DeviceRuns"][-1]["EndTime"] is None:
                    end_time = dt.datetime.combine(last_day["Date"], dt.time(23, 59, 59))
                    self.stop_run(StateReasonOff.DAY_END, status_data, end_time)

            # Check the energy usage for yesterdat and send email if needed
            self._check_yesterday_energy_usage()

        self._update_totals(status_data)
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

    def _check_yesterday_energy_usage(self):
        """Check if the energy used yesterday was more than expected."""
        prior_energy_used = self.history["DailyData"][-1]["EnergyUsed"] if self.history["DailyData"] else 0
        threashold = self.output_config.get("MaxDailyEnergyUse", 0) or 0
        if prior_energy_used == 0 or threashold == 0:
            return  # No data to check

        if prior_energy_used > threashold:
            warning_msg = f"{self.output_config.get("Name")} output used on {prior_energy_used:.0f}W, which exceeded the expected limit of {threashold}W."
            self.logger.log_message(warning_msg, "warning")

            # Send an email notification if configured
            self.logger.send_email("Energy Usage Alert", warning_msg)

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

    def start_run(self, new_system_state: SystemState, reason: StateReasonOn, status_data: OutputStatusData):
        """Add a new run instance to the history.

        Args:
            new_system_state (SystemState): The system state when the run started.
            reason (StateReasonOn): The reason why the output was turned on.
            status_data (OutputStatusData): The status data for the associated output.
        """
        start_time = DateHelper.now()

        current_run = self.get_current_run()
        if current_run is not None:
            if current_run["SystemState"] == new_system_state and current_run["ReasonStarted"] == reason:
                # Already running with the same state and reason, no action needed
                return
            # Stop the current run before starting a new one
            self.stop_run(StateReasonOff.STATUS_CHANGE, status_data)

        new_run = self._create_run_object(start_time, status_data)
        new_run["SystemState"] = new_system_state
        new_run["ReasonStarted"] = reason

        # Find or create today's day object and append the new run
        today = DateHelper.today()
        if not self.history["DailyData"] or self.history["DailyData"][-1]["Date"] != today:
            day_obj = self._create_day_object(today, status_data)
            self.history["DailyData"].append(day_obj)
        self.history["DailyData"][-1]["DeviceRuns"].append(new_run)

        self._update_totals(status_data)

    def stop_run(self, reason: StateReasonOff, status_data: OutputStatusData, stop_time: dt.datetime | None = None):
        """Stop the current active run and update its details.

        Args:
            reason (StateReasonOff): The reason why the output was turned off.
            status_data (OutputStatusData): The status data for the associated output.
            stop_time (dt.datetime | None): The time when the run was stopped. Defaults to now if not provided.
        """
        current_run = self.get_current_run()
        if current_run is None:
            # No active run to stop
            return

        # Calculate the totals for this run
        self._calculate_values_for_open_run(status_data)  # This will calculate energy used, actual hours, average price
        current_run["EndTime"] = DateHelper.now() if stop_time is None else stop_time
        current_run["ReasonStopped"] = reason

        self._update_totals(status_data)

    def _calculate_values_for_open_run(self, status_data: OutputStatusData):
        """Calculate the values for the current open run.

        Args:
            status_data (OutputStatusData): The status data for the associated output.
        """
        current_run = self.get_current_run()
        if current_run is None:
            return

        current_time = DateHelper.now()
        current_run["ActualHours"] = (current_time - current_run["StartTime"]).total_seconds() / 3600.0

        last_meter_read = current_run["PriorMeterRead"]
        current_run["LastActualPrice"] = status_data.current_price
        if status_data.meter_reading > 0.0 and last_meter_read > 0.0 and status_data.meter_reading > last_meter_read:
            # We have used some energy since the last call to this func
            energy_used = status_data.meter_reading - last_meter_read
            current_run["EnergyUsed"] += energy_used
            current_run["TotalCost"] += self.calc_cost(energy_used, status_data.current_price)
            current_run["AveragePrice"] = self.calc_price(current_run["EnergyUsed"], current_run["TotalCost"])

            # Make a note of the most recent read so that we don't re-do this code
            current_run["PriorMeterRead"] = status_data.meter_reading

    def _update_totals(self, status_data: OutputStatusData):
        """Update all the running totals in the history object.

        Args:
            status_data (OutputStatusData): The status data for the associated output.
        """
        # If we don't have a day entry for today, create it
        if not self.history["DailyData"] or self.history["DailyData"][-1]["Date"] != DateHelper.today():
            new_day = self._create_day_object(DateHelper.today(), status_data)
            self.history["DailyData"].append(new_day)

        # If we currently have a run open, calculate energy used, actual hours, average price
        self._calculate_values_for_open_run(status_data)

        # Reset the CurrentTotals
        self.history["CurrentTotals"]["EnergyUsed"] = 0
        self.history["CurrentTotals"]["TotalCost"] = 0.0
        self.history["CurrentTotals"]["ActualHours"] = 0.0
        self.history["CurrentTotals"]["AveragePrice"] = 0.0

        # Set a default for the AlltimeTotals in case we don't have anything to process
        self.history["AlltimeTotals"]["EnergyUsed"] = self.history["EarlierTotals"]["EnergyUsed"]
        self.history["AlltimeTotals"]["HourlyEnergyUsed"] = self.history["EarlierTotals"].get("HourlyEnergyUsed", 0.0)
        self.history["AlltimeTotals"]["TotalCost"] = self.history["EarlierTotals"]["TotalCost"]
        self.history["AlltimeTotals"]["ActualHours"] = self.history["EarlierTotals"]["ActualHours"]
        self.history["AlltimeTotals"]["AveragePrice"] = self.history["EarlierTotals"]["AveragePrice"]

        # Now iterate through each day if we have anything to do
        # Set the prior_shortfall to be the current value for the earliest day
        oldest_day = self.history["DailyData"][0]
        running_shortfall = oldest_day["PriorShortfall"] if self.run_plan_target_mode == RunPlanTargetHours.NORMAL else 0.0

        for day in self.history["DailyData"]:
            # Calculate the running total for this day
            day["PriorShortfall"] = max(0, min(self.max_shortfall_hours, running_shortfall))
            # Note: TargetHours will be set when we add the day

            # Reset the totals for this day
            day["ActualHours"] = 0.0
            day["EnergyUsed"] = 0
            day["HourlyEnergyUsed"] = 0.0
            day["TotalCost"] = 0.0
            day["AveragePrice"] = 0.0

            # Loop through each device run (including any open run) and update the daily totals
            for run in day["DeviceRuns"]:
                day["ActualHours"] += run["ActualHours"]
                day["EnergyUsed"] += run["EnergyUsed"]
                day["TotalCost"] += run["TotalCost"]

            # Hourly energy used is simply energy used divided by actual hours
            day["HourlyEnergyUsed"] = day["EnergyUsed"] / day["ActualHours"] if day["ActualHours"] > 0 else 0.0

            # Now calculate average price for this day
            day["AveragePrice"] = self.calc_price(day["EnergyUsed"], day["TotalCost"])

            # Now add the day's totals to the global CurrentTotals
            self.history["CurrentTotals"]["EnergyUsed"] += day["EnergyUsed"]
            self.history["CurrentTotals"]["TotalCost"] += day["TotalCost"]
            self.history["CurrentTotals"]["ActualHours"] += day["ActualHours"]
            self.history["CurrentTotals"]["HourlyEnergyUsed"] = self.history["CurrentTotals"]["EnergyUsed"] / self.history["CurrentTotals"]["ActualHours"] if self.history["CurrentTotals"]["ActualHours"] > 0 else 0.0

            # Adjust running_shortfall for the next day
            running_shortfall += status_data.target_hours - day["ActualHours"] if status_data.target_hours is not None else 0.0

        # Calculate the remaining values for CurrentTotals
        self.history["CurrentTotals"]["AveragePrice"] = self.calc_price(self.history["CurrentTotals"]["EnergyUsed"], self.history["CurrentTotals"]["TotalCost"])

        # Finally calculate the values for AlltimeTotals
        self.history["AlltimeTotals"]["EnergyUsed"] = self.history["CurrentTotals"]["EnergyUsed"] + self.history["EarlierTotals"]["EnergyUsed"]
        self.history["AlltimeTotals"]["TotalCost"] = self.history["CurrentTotals"]["TotalCost"] + self.history["EarlierTotals"]["TotalCost"]
        self.history["AlltimeTotals"]["ActualHours"] = self.history["CurrentTotals"]["ActualHours"] + self.history["EarlierTotals"]["ActualHours"]
        self.history["AlltimeTotals"]["AveragePrice"] = self.calc_price(self.history["AlltimeTotals"]["EnergyUsed"], self.history["AlltimeTotals"]["TotalCost"])
        self.history["AlltimeTotals"]["HourlyEnergyUsed"] = self.history["AlltimeTotals"]["EnergyUsed"] / self.history["AlltimeTotals"]["ActualHours"] if self.history["AlltimeTotals"]["ActualHours"] > 0 else 0.0

        self.history["LastUpdate"] = DateHelper.now()
        self.history["HistoryDays"] = len(self.history["DailyData"])
        current_run = self.get_current_run()
        self.history["LastStartTime"] = current_run["StartTime"] if current_run else None
        self.history["LastMeterRead"] = status_data.meter_reading
        self.history["CurrentPrice"] = status_data.current_price

    def get_actual_hours(self) -> float:
        """Returns the total actual hours from the run history."""
        if self.history["DailyData"]:
            return self.history["DailyData"][-1]["ActualHours"]
        return 0.0

    def get_prior_shortfall(self) -> float:
        """Returns the total prior shortfall from the run history. Amount is adjusted for any maximum shortfall hours configured."""
        if self.history["DailyData"]:
            return self.history["DailyData"][-1]["PriorShortfall"]
        return 0.0

    def get_hourly_energy_used(self) -> float:
        """Returns the average hourly energy used from the run history. Returns data for the most recent day or prior day if today has only recently started."""
        if self.history["DailyData"]:
            for day in reversed(self.history["DailyData"]):
                if day["ActualHours"] >= 2 and day["HourlyEnergyUsed"] > 0.0:
                    return day["HourlyEnergyUsed"]
        return 0.0

    @staticmethod
    def calc_cost(energy_used: float, price: float) -> float:
        """Calculate the cost in $ given energy used in Wh and price in c/kWh.

        Args:
            energy_used (float): The energy used in Wh.
            price (float): The price in c/kWh.

        Returns:
            float: Total cost in $.
        """
        return (energy_used / 1000) * (price / 100) if energy_used > 0 else 0

    @staticmethod
    def calc_price(energy_used: float, total_cost: float) -> float:
        """Calculate the average price in c/kWh given energy used in Wh and total cost in cents.

        Args:
            energy_used (float): The energy used in Wh.
            total_cost (float): The total cost in $.

        Returns:
            float: The average price in c/kWh.
        """
        return (total_cost / (energy_used / 1000)) * 100 if energy_used > 0 else 0
