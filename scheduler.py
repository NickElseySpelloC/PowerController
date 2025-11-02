"""Scheduler module for managing the time based schedules for each switch."""

import datetime as dt
import operator
import re

import pytz
from astral import LocationInfo
from astral.sun import sun
from org_enums import RunPlanMode
from sc_utility import DateHelper, SCConfigManager, SCLogger

from local_enumerations import DEFAULT_PRICE, WEEKDAY_ABBREVIATIONS
from run_plan import RunPlanner


class Scheduler:
    """Scheduler class to manage the time based schedules for each switch."""
    def __init__(self, config: SCConfigManager, logger: SCLogger):
        """Initialise the scheduler class.

        Args:
            config (SCConfigManager): The configuration manager for the system.
            logger (SCLogger): The logger for the system.
        """
        self.config = config
        self.logger = logger
        self.schedules = []

        self.initialise()

    def initialise(self):
        """Initialise the scheduler and load the schedules from config."""
        self.schedules = self.config.get("OperatingSchedules", default=[])
        if not isinstance(self.schedules, list) or not self.schedules:
            self.logger.log_message("No OperatingSchedules configured in the config file.", "warning")
        assert isinstance(self.schedules, list)

        # Validate that each has at least one StartTime/EndTime pair.
        for schedule in self.schedules:
            for window in schedule.get("Windows", []):
                if not window.get("StartTime") or not window.get("EndTime"):
                    self.logger.log_fatal_error(f"Schedule '{schedule.get('Name')}' must have at least one StartTime and EndTime.")
                    continue

        self.dusk_dawn = self._get_dusk_dawn_times()
        self.default_price = self.config.get("General", "DefaultPrice", default=DEFAULT_PRICE) or DEFAULT_PRICE
        assert isinstance(self.default_price, (int, float)) and self.default_price >= 0, "DefaultPrice must be a non-negative number"  # noqa: PT018

    def get_save_object(self, schedule: dict | None = None) -> dict:
        """Returns the representation of this scheduler object that can be saved to disk.

        Args:
            schedule (dict | None): The schedule to include in the save object.

        Returns:
            dict: The representation of the scheduler object.
        """
        if schedule:
            schedule_dict = {
                "Schedule": schedule,
                "Dawn": self.dusk_dawn.get("dawn") if self.dusk_dawn else None,
                "Dusk": self.dusk_dawn.get("dusk") if self.dusk_dawn else None,
            }
            return schedule_dict

        schedule_dict = {
            "Schedules": self.schedules,
            "Dawn": self.dusk_dawn.get("dawn") if self.dusk_dawn else None,
            "Dusk": self.dusk_dawn.get("dusk") if self.dusk_dawn else None,
        }
        return schedule_dict

    def get_schedule_by_name(self, name: str) -> dict | None:
        """Retrieve a schedule by its name from the configuration.

        Args:
            name (str): The name of the schedule to retrieve.

        Returns:
            dict: The schedule dictionary if found, or None if not found.
        """
        if not isinstance(self.schedules, list):
            self.logger.log_message("No OperatingSchedules configured in the config file.", "warning")
            return None
        for schedule in self.schedules:
            if schedule.get("Name") == name:
                return schedule
        return None

    def get_run_plan(self,
                     operating_schedule_name: str,
                     required_hours: float,
                     priority_hours: float,
                     max_price: float,
                     max_priority_price: float,
                     hourly_energy_usage: float = 0.0,
                     slot_min_minutes: int = 0,
                     slot_min_gap_minutes: int = 0) -> dict | None:
        """Calculate the best time(s) to run based on the configured schedule.

        Work throught the Start/Stop times in preference order.
        If required_hours is None, it uses all window hours in the current day.

        Args:
            operating_schedule_name (str): The name of the operating schedule to use.
            required_hours (float): The number of hours required for the task. Set to -1 to get all remaining hours that can be filled.
            priority_hours (float): The number of hours that should be prioritized.
            max_price (float): The maximum price to consider for the run plan.
            max_priority_price (float): The maximum price to consider for priority hours in the run plan.
            hourly_energy_usage (float): The average hourly energy usage in Wh. Used to estimate cost of the run plan.
            slot_min_minutes (int): The minimum length of each time slot in minutes.
            slot_min_gap_minutes (int): The minimum gap between time slots in minutes.

        Returns:
            dict | None: The run plan if successful, None if failed.
        """
        # Lookup the schedule by name
        schedule = self.get_schedule_by_name(operating_schedule_name)
        if not schedule:
            self.logger.log_message(f"Schedule '{operating_schedule_name}' not found.", "error")
            return None

        # Get the available window time slots for this schedule
        time_slots = self._get_schedule_slots(schedule)
        sorted_slots = sorted(time_slots, key=operator.itemgetter("Price"))
        if not time_slots:
            self.logger.log_message(f"No available time slots found for schedule {operating_schedule_name} for today.", "debug")
            return None

        try:
            # Create a run planner instance
            run_planner = RunPlanner(self.logger, RunPlanMode.SCHEDULE)
            self.logger.log_message(f"Calculating schedule {operating_schedule_name} run plan for {required_hours} hours ({priority_hours} priority) with max prices {max_price} / {max_priority_price}.", "debug")

            run_plan = run_planner.calculate_run_plan(sorted_slots, required_hours, priority_hours, max_price, max_priority_price, hourly_energy_usage, slot_min_minutes, slot_min_gap_minutes)
        except RuntimeError as e:
            self.logger.log_message(f"Error occurred while calculating schedule run plan: {e}", "error")
            return None
        else:
            return run_plan

    def _get_schedule_slots(self, schedule: dict) -> list[dict]:
        """Evaluate the schedule and return a list of time slots when the schedule is active for today.

        Args:
            schedule (dict): The schedule dictionary.

        Returns:
            list[dict]: A list of time slots. May be empty.
        """
        time_slots = []

        # Get the 3 letter abbreviation for the current weekday
        today = DateHelper.today()
        weekday_str = WEEKDAY_ABBREVIATIONS[today.weekday()]
        time_now = DateHelper.now().time().replace(second=0, microsecond=0)
        local_tz = dt.datetime.now().astimezone().tzinfo

        # Loop through each window in the provided schedule
        for idx, window in enumerate(schedule.get("Windows", [])):
            days = window.get("DaysOfWeek", "All")
            if days != "All" and weekday_str not in [d.strip() for d in days.split(",")]:
                continue    # Event is constrained to specific days that doesn't include today

            start_time = self._parse_time(window["StartTime"], schedule["Name"], idx)
            end_time = self._parse_time(window["EndTime"], schedule["Name"], idx)

            # If this schedule window has already ended, skip it
            if end_time < time_now:
                continue

            # If the start of this schedule window is in the past, adjust the start time
            if end_time > time_now and start_time < time_now:
                start_time = max(start_time, time_now)

            # need datetime versions to calculate minutes
            start_dt = dt.datetime.combine(today, start_time, tzinfo=local_tz)
            end_dt = dt.datetime.combine(today, end_time, tzinfo=local_tz)

            time_slot = {
                "Date": today,
                "StartTime": start_time,
                "StartDateTime": start_dt,
                "EndTime": end_time,
                "EndDateTime": end_dt,
                "Minutes": int((end_dt - start_dt).total_seconds() // 60),
                "Price": window.get("Price", self.default_price) or self.default_price
            }

            if time_slot["StartTime"] is None or time_slot["EndTime"] is None:
                continue

            time_slots.append(time_slot)

        return time_slots

    def _parse_time(self, time_str, schedule_name, window_index) -> dt.time:
        """Parse a time string. Exits if the time string is invalid.

        The time stings are found in the StartTime and EndTime fields of the OperatingSchedules: Windows section of the config file and can be any of these types:
        - "HH:MM" format (e.g., "14:30")
        - "dawn" or "dusk" with optional hh:mm offset (e.g., "dawn+00:10" or "dusk-01:30")

        Args:
            time_str (str): The time string to parse, can be in "HH:MM" format or "dawn" / "dusk" with optional offset.
            schedule_name (str): The name of the schedule for logging.
            window_index (int): The index of the window in the schedule.

        Returns:
            time: The parsed time.
        """
        local_tz = dt.datetime.now().astimezone().tzinfo

        if not self.dusk_dawn:
            self.logger.log_fatal_error(f"Dawn/Dusk times have not been set for schedule '{schedule_name}', window {window_index}")

        # Check for dawn/dusk with optional offset
        if time_str.lower().startswith(("dawn", "dusk")):
            # Extract base time type and any offset
            if time_str.lower().startswith("dawn"):
                base_time = self.dusk_dawn["dawn"]
                offset_part = time_str[4:]  # Everything after "dawn"
            else:  # dusk
                base_time = self.dusk_dawn["dusk"]
                offset_part = time_str[4:]  # Everything after "dusk"

            # Parse any dawn/dusk time offset (e.g., "+00:10" or "-01:30")
            if offset_part:
                try:
                    # Match pattern like "+00:10" or "-01:30"
                    match = re.match(r"^([+-])(\d{2}):(\d{2})$", offset_part)
                    if match:
                        sign, hours, minutes = match.groups()
                        total_minutes = int(hours) * 60 + int(minutes)
                        if sign == "-":
                            total_minutes = -total_minutes

                        # Apply the offset to base_time
                        base_datetime = dt.datetime.combine(DateHelper.today(), base_time)
                        adjusted_datetime = base_datetime + dt.timedelta(minutes=total_minutes)
                        base_time = adjusted_datetime.time()
                    else:
                        self.logger.log_fatal_error(f"Invalid dawn/dusk offset format for the schedule '{schedule_name}', time entry '{time_str}'. Use format like 'Dawn+00:10' or 'Dusk-01:30'")
                except (ValueError, TypeError, OSError):
                    self.logger.log_fatal_error(f"Invalid dawn/dusk offset format for the schedule '{schedule_name}', time entry '{time_str}'. Use format like 'Dawn+00:10' or 'Dusk-01:30'")
        else:
            try:
                base_time = dt.datetime.strptime(time_str, "%H:%M").replace(tzinfo=local_tz).time()
            except ValueError:
                self.logger.log_fatal_error(f"Invalid time format for the schedule '{schedule_name}', time entry '{time_str}'. Use format like 'HH:MM'")

        return base_time  # pyright: ignore[reportPossiblyUnboundVariable]

    def _get_dusk_dawn_times(self) -> dict:
        """Get the dawn and dusk times based on the location returned from the specified shelly switch or the manually configured location configuration.

        Returns:
            dict: A dictionary with 'dawn' and 'dusk' times.
        """
        name = "PowerController"
        loc_conf = self.config.get("Location", default={})
        assert isinstance(loc_conf, dict), "Location configuration must be a dictionary"
        tz = lat = lon = None

        # TO DO: Move this to the ShellyWorker thread
        # shelly_device_name = loc_conf.get("UseShellyDevice")
        # if shelly_device_name:
        #     # Get the tz, lat and long from the specified Shelly device
        #     try:
        #         device = self.shelly_control.get_device(shelly_device_name)
        #         shelly_loc = self.shelly_control.get_device_location(device)
        #         if shelly_loc:
        #             tz = shelly_loc.get("tz")
        #             lat = shelly_loc.get("lat")
        #             lon = shelly_loc.get("lon")
        #     except (RuntimeError, TimeoutError) as e:
        #         self.logger.log_message(f"Error getting location from Shelly device {shelly_device_name}: {e}", "warning")

        # If we were unable to get the location from the Shelly device, see if we can extract it from the Google Maps url (if supplied)
        if tz is None:
            tz = loc_conf["Timezone"]
            # Extract coordinates
            if "GoogleMapsURL" in loc_conf and loc_conf["GoogleMapsURL"] is not None:
                url = loc_conf["GoogleMapsURL"]
                match = re.search(r"@?([-]?\d+\.\d+),([-]?\d+\.\d+)", url)
                if match:
                    lat = float(match.group(1))
                    lon = float(match.group(2))
            else:   # Last resort, try the config values
                lat = loc_conf["Latitude"]
                lon = loc_conf["Longitude"]

        if lat is None or lon is None:
            self.logger.log_message("Latitude and longitude could not be determined, using defaults for 0°00'00\"N 0°00'00.0\"E.", "warning")
            lat = 0.0
            lon = 0.0

        # Create location object and compute times
        location = LocationInfo(name=name, region="", timezone=tz, latitude=lat, longitude=lon)
        s = sun(location.observer, date=DateHelper.today(), tzinfo=pytz.timezone(tz))

        return {
            "dawn": s["dawn"].time(),
            "dusk": s["dusk"].time(),
        }

    def get_current_price(self, schedule: dict) -> float:
        """Get the current price from the pricing manager.

        Args:
            schedule (dict): The schedule dictionary.

        Returns:
            float: The current price in AUD/kWh, or 0 if not available.
        """
        # Get the slots for the current time
        slots = self._get_schedule_slots(schedule)
        if not slots:
            return self.default_price  # pyright: ignore[reportReturnType]

        # See if we have a slot that encompasses the current time
        current_time = DateHelper.now().time()
        for slot in slots:
            if slot["StartTime"] <= current_time <= slot["EndTime"]:
                # Get the current price from the pricing manager
                return slot["Price"]

        return self.default_price  # pyright: ignore[reportReturnType]
