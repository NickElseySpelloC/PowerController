"""Scheduler module for managing the time based schedules for each switch."""

import datetime as dt
import operator
import re

from org_enums import RunPlanMode
from sc_foundation import DateHelper, SCConfigManager, SCLogger

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

        self.power_tariff = self.config.get("PowerTariff", default=None)
        if self.power_tariff:
            self._validate_tariff_coverage()

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
        time_slots = self.get_schedule_slots(schedule)
        if not time_slots:
            self.logger.log_message(f"No available time slots found for schedule {operating_schedule_name} for today.", "debug")
            sorted_slots = []
        else:
            sorted_slots = sorted(time_slots, key=operator.itemgetter("Price"))

        try:
            # Create a run planner instance
            run_planner = RunPlanner(self.logger, RunPlanMode.SCHEDULE)
            self.logger.log_message(f"Calculating schedule {operating_schedule_name} run plan for {required_hours:.2f} hours ({priority_hours:.2f} priority) with max prices {max_price} / {max_priority_price}.", "debug")

            run_plan = run_planner.calculate_run_plan(sorted_slots, required_hours, priority_hours, max_price, max_priority_price, hourly_energy_usage, slot_min_minutes, slot_min_gap_minutes)
        except RuntimeError as e:
            self.logger.log_message(f"Error occurred while calculating schedule run plan: {e}", "error")
            return None
        else:
            return run_plan

    def get_current_price(self, schedule: dict) -> float:
        """Get the current price from the schedule for the current time.

        Args:
            schedule (dict): The schedule dictionary.

        Returns:
            float: The current price in AUD/kWh, or 0 if not available.
        """
        # Get the slots for the current time
        slots = self.get_schedule_slots(schedule)
        if not slots:
            return self.default_price  # pyright: ignore[reportReturnType]

        # See if we have a slot that encompasses the current time
        current_time = DateHelper.now().time()
        for slot in slots:
            if slot["StartTime"] <= current_time <= slot["EndTime"]:
                # Get the current price from the pricing manager
                return slot["Price"]

        return self.default_price  # pyright: ignore[reportReturnType]

    def get_price(self, schedule: dict, as_at_time: dt.datetime) -> float:
        """Get the price from the schedule at the specified time.

        Args:
            schedule (dict): The schedule dictionary.
            as_at_time (dt.datetime): The datetime to get the price for.

        Returns:
            float: The current price in AUD/kWh, or 0 if not available.
        """
        # Get the slots for the current time
        slots = self.get_schedule_slots(schedule)
        if not slots:
            return self.default_price  # pyright: ignore[reportReturnType]

        # See if we have a slot that encompasses the current time
        lookup_time = as_at_time.time()
        for slot in slots:
            if slot["StartTime"] <= lookup_time <= slot["EndTime"]:
                return slot["Price"]

        return self.default_price  # pyright: ignore[reportReturnType]

    def save_device_location_info(self, loc_info: dict[str, dict]):
        """Accept the device location info dictionary from the controller and store it for use in dawn/dusk calculations.

        Args:
            loc_info (dict): The location information dictionary. A dict of location data, keyed by a Shelly device name.
        """
        self.dusk_dawn = self._get_dusk_dawn_times(loc_info)

    def get_schedule_slots(self, schedule: dict) -> list[dict]:
        """Evaluate the schedule and return a list of time slots when the schedule is active for today.

        When EndTime <= StartTime the window is treated as overnight (spanning midnight). The
        DaysOfWeek applicability is determined by the StartTime's day. Two contributions are
        considered for each overnight window:
          - Yesterday's tail: the window started yesterday and is still running into today
            (00:00 → EndTime). Included only if it hasn't yet ended.
          - Today's head: the window starts today and runs past midnight (StartTime → 23:59 today,
            with EndDateTime set to tomorrow's EndTime so that Minutes spans the full overnight
            duration). The special case of StartTime == EndTime == "00:00" is treated as a
            full 24-hour day window.

        Args:
            schedule (dict): The schedule dictionary.

        Returns:
            list[dict]: A list of time slots. May be empty.
        """
        time_slots = []

        today = DateHelper.today()
        tomorrow = DateHelper.today_add_days(1)
        weekday_str = WEEKDAY_ABBREVIATIONS[today.weekday()]
        yesterday_str = WEEKDAY_ABBREVIATIONS[(today.weekday() - 1) % 7]
        time_now = DateHelper.now().time().replace(second=0, microsecond=0)

        use_tariff = schedule.get("UsePowerTariff") and self.power_tariff

        for idx, window in enumerate(schedule.get("Windows", [])):
            days = window.get("DaysOfWeek", "All")
            price = window.get("Price", self.default_price) or self.default_price

            start_time = self._parse_time(window["StartTime"], schedule["Name"], idx)
            end_time = self._parse_time(window["EndTime"], schedule["Name"], idx)

            if start_time is None or end_time is None:
                continue

            is_overnight = end_time <= start_time

            if is_overnight:
                # --- Yesterday's tail: window started yesterday, still running into today ---
                yesterday_applies = days == "All" or yesterday_str in [d.strip() for d in days.split(",")]
                if yesterday_applies and end_time > time_now:
                    tail_start_dt = DateHelper.combine(today, time_now)
                    tail_end_dt = DateHelper.combine(today, end_time)
                    tail_slot = {
                        "Date": today,
                        "StartTime": time_now,
                        "StartDateTime": tail_start_dt,
                        "EndTime": end_time,
                        "EndDateTime": tail_end_dt,
                        "Minutes": int((tail_end_dt - tail_start_dt).total_seconds() // 60),
                        "Price": price,
                    }
                    if use_tariff:
                        time_slots.extend(self._get_tariff_slots_for_window(tail_slot, today))
                    else:
                        time_slots.append(tail_slot)

                # --- Today's head: window starts today, runs past midnight ---
                today_applies = days == "All" or weekday_str in [d.strip() for d in days.split(",")]
                if today_applies:
                    head_start = max(start_time, time_now) if start_time < time_now else start_time
                    head_start_dt = DateHelper.combine(today, head_start)
                    head_end_dt = DateHelper.combine(tomorrow, end_time)
                    if head_start_dt < head_end_dt:
                        head_slot = {
                            "Date": today,
                            "StartTime": head_start,
                            "StartDateTime": head_start_dt,
                            "EndTime": dt.time(23, 59),  # capped for same-day time comparisons
                            "EndDateTime": head_end_dt,  # crosses midnight for correct Minutes
                            "Minutes": int((head_end_dt - head_start_dt).total_seconds() // 60),
                            "Price": price,
                        }
                        if use_tariff:
                            time_slots.extend(self._get_tariff_slots_for_window(head_slot, today))
                        else:
                            time_slots.append(head_slot)

            else:
                # --- Normal same-day window ---
                if days != "All" and weekday_str not in [d.strip() for d in days.split(",")]:
                    continue

                # If this schedule window has already ended, skip it
                if end_time < time_now:
                    continue

                # If the start of this schedule window is in the past, adjust the start time
                if start_time < time_now:
                    start_time = time_now

                start_dt = DateHelper.combine(today, start_time)
                end_dt = DateHelper.combine(today, end_time)

                time_slot = {
                    "Date": today,
                    "StartTime": start_time,
                    "StartDateTime": start_dt,
                    "EndTime": end_time,
                    "EndDateTime": end_dt,
                    "Minutes": int((end_dt - start_dt).total_seconds() // 60),
                    "Price": price,
                }

                if use_tariff:
                    time_slots.extend(self._get_tariff_slots_for_window(time_slot, today))
                else:
                    time_slots.append(time_slot)

        return time_slots

    # Private Functions ===========================================================================

    def _get_tariff_slots_for_window(self, base_slot: dict, today: dt.date) -> list[dict]:
        """Split a schedule slot into sub-slots aligned to tariff band boundaries.

        For each sub-slot the price comes from the first matching tariff band. If a sub-slot
        falls in a gap (no tariff coverage) the schedule window's own price is used instead.

        Midnight-spanning bands (EndTime < StartTime, e.g. 23:00–07:00) contribute two
        ranges to today's coverage: the tail of the band that started yesterday (00:00–end)
        and the head of the band that starts today (start–24:00).

        Args:
            base_slot (dict): A single slot as produced by get_schedule_slots() before tariff expansion.
            today (dt.date): The date of the slot (used for day-of-week matching).

        Returns:
            list[dict]: One or more slots covering the same time range as base_slot.
        """
        weekday_str = WEEKDAY_ABBREVIATIONS[today.weekday()]
        yesterday_str = WEEKDAY_ABBREVIATIONS[(today.weekday() - 1) % 7]

        # Build a list of (start_minutes, end_minutes, price) covering today.
        # A midnight-spanning band contributes a 0..e_min segment from yesterday's band
        # and a s_min..1440 segment from today's band.
        tariff_bands: list[tuple[int, int, float]] = []
        for band in self.power_tariff:  # type: ignore[union-attr]
            days = band.get("DaysOfWeek", "All")
            applies_today = days == "All" or weekday_str in [d.strip() for d in days.split(",")]
            applies_yesterday = days == "All" or yesterday_str in [d.strip() for d in days.split(",")]
            try:
                band_start = dt.datetime.strptime(band["StartTime"], "%H:%M").time()
                band_end = dt.datetime.strptime(band["EndTime"], "%H:%M").time()
            except (ValueError, KeyError):
                continue
            s_min = band_start.hour * 60 + band_start.minute
            e_min = band_end.hour * 60 + band_end.minute
            price = band.get("Price") or self.default_price
            if e_min <= s_min:
                # Midnight-spanning band
                if applies_today:
                    tariff_bands.append((s_min, 24 * 60, price))   # type: ignore[arg-type]
                if applies_yesterday:
                    tariff_bands.append((0, e_min, price))          # type: ignore[arg-type]
            else:
                if applies_today:
                    tariff_bands.append((s_min, e_min, price))      # type: ignore[arg-type]

        # Collect boundary minutes within the slot's range, then split
        slot_start_min = base_slot["StartTime"].hour * 60 + base_slot["StartTime"].minute
        slot_end_min = base_slot["EndTime"].hour * 60 + base_slot["EndTime"].minute

        boundaries: set[int] = {slot_start_min, slot_end_min}
        for s, e, _ in tariff_bands:
            if slot_start_min < s < slot_end_min:
                boundaries.add(s)
            if slot_start_min < e < slot_end_min:
                boundaries.add(e)

        sorted_boundaries = sorted(boundaries)
        result: list[dict] = []

        for i in range(len(sorted_boundaries) - 1):
            sub_start_min = sorted_boundaries[i]
            sub_end_min = sorted_boundaries[i + 1]

            # Determine price: first matching tariff band wins, else fall back to schedule price
            sub_price = base_slot["Price"]
            for s, e, p in tariff_bands:
                if s <= sub_start_min and sub_end_min <= e:
                    sub_price = p
                    break

            sub_start = dt.time(sub_start_min // 60, sub_start_min % 60)
            sub_end = dt.time(sub_end_min // 60, sub_end_min % 60)
            sub_start_dt = DateHelper.combine(today, sub_start)
            sub_end_dt = DateHelper.combine(today, sub_end)
            result.append({
                "Date": today,
                "StartTime": sub_start,
                "StartDateTime": sub_start_dt,
                "EndTime": sub_end,
                "EndDateTime": sub_end_dt,
                "Minutes": int((sub_end_dt - sub_start_dt).total_seconds() // 60),
                "Price": sub_price,
            })

        return result if result else [base_slot]

    def _validate_tariff_coverage(self):
        """Log warnings for any minutes of the week not covered by a tariff band."""
        MINUTES_PER_DAY = 24 * 60
        for day_idx, day_name in enumerate(WEEKDAY_ABBREVIATIONS):
            yesterday_name = WEEKDAY_ABBREVIATIONS[(day_idx - 1) % 7]
            covered = [False] * MINUTES_PER_DAY
            for band in self.power_tariff:  # type: ignore[union-attr]
                days = band.get("DaysOfWeek", "All")
                applies_today = days == "All" or day_name in [d.strip() for d in days.split(",")]
                applies_yesterday = days == "All" or yesterday_name in [d.strip() for d in days.split(",")]
                try:
                    band_start = dt.datetime.strptime(band["StartTime"], "%H:%M").time()
                    band_end = dt.datetime.strptime(band["EndTime"], "%H:%M").time()
                except (ValueError, KeyError):
                    continue
                s_min = band_start.hour * 60 + band_start.minute
                e_min = band_end.hour * 60 + band_end.minute
                if e_min <= s_min:
                    # Midnight-spanning band: today's portion is s_min..1440, yesterday's wrap is 0..e_min
                    if applies_today:
                        for m in range(s_min, MINUTES_PER_DAY):
                            covered[m] = True
                    if applies_yesterday:
                        for m in range(0, e_min):
                            covered[m] = True
                else:
                    if applies_today:
                        for m in range(s_min, e_min):
                            covered[m] = True

            # Report gaps as contiguous uncovered ranges
            gap_start: int | None = None
            for m in range(MINUTES_PER_DAY + 1):
                in_gap = m < MINUTES_PER_DAY and not covered[m]
                if in_gap and gap_start is None:
                    gap_start = m
                elif not in_gap and gap_start is not None:
                    gap_s = dt.time(gap_start // 60, gap_start % 60)
                    gap_e = dt.time(m // 60, m % 60) if m < MINUTES_PER_DAY else dt.time(23, 59)
                    self.logger.log_message(
                        f"PowerTariff: no tariff band covers {day_name} {gap_s.strftime('%H:%M')}–{gap_e.strftime('%H:%M')}",
                        "warning",
                    )
                    gap_start = None

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
                        base_datetime = DateHelper.combine(DateHelper.today(), base_time)
                        adjusted_datetime = DateHelper.add_datetime(base_datetime, minutes=total_minutes)
                        assert isinstance(adjusted_datetime, dt.datetime)
                        base_time = adjusted_datetime.time()
                    else:
                        self.logger.log_fatal_error(f"Invalid dawn/dusk offset format for the schedule '{schedule_name}', time entry '{time_str}'. Use format like 'Dawn+00:10' or 'Dusk-01:30'")
                except (ValueError, TypeError, OSError):
                    self.logger.log_fatal_error(f"Invalid dawn/dusk offset format for the schedule '{schedule_name}', time entry '{time_str}'. Use format like 'Dawn+00:10' or 'Dusk-01:30'")
        else:
            try:
                base_time = DateHelper.extract_time(time_str, "%H:%M")
            except ValueError:
                self.logger.log_fatal_error(f"Invalid time format for the schedule '{schedule_name}', time entry '{time_str}'. Use format like 'HH:MM'")

        return base_time  # pyright: ignore[reportPossiblyUnboundVariable]

    def _get_dusk_dawn_times(self, loc_info: dict[str, dict] | None = None) -> dict:
        """Get the dawn and dusk times based on the location returned from the specified shelly switch or the manually configured location configuration.

        Args:
            loc_info (dict): The location information dictionary. A dict of location data, keyed by Shelly device name.

        Returns:
            dict: A dictionary with 'dawn' and 'dusk' times.
        """
        loc_conf = self.config.get("Location", default={})
        assert isinstance(loc_conf, dict), "Location configuration must be a dictionary"
        tz = lat = lon = None

        # See if we have a Shelly device specified to get the location from
        device_name = loc_conf.get("UseShellyDevice")
        if device_name:
            # Get the tz, lat and long from the specified device
            loc = loc_info.get(device_name, {}) if loc_info else None
            if loc:
                tz = loc.get("tz")
                lat = loc.get("lat")
                lon = loc.get("lon")

        # If we were unable to get the location from the device, see if we can extract it from the Google Maps url (if supplied)
        if tz is None:
            tz = loc_conf.get("Timezone")
            # Extract coordinates
            if "GoogleMapsURL" in loc_conf and loc_conf["GoogleMapsURL"] is not None:
                url = loc_conf["GoogleMapsURL"]
                match = re.search(r"@?([-]?\d+\.\d+),([-]?\d+\.\d+)", url)
                if match:
                    lat = float(match.group(1))
                    lon = float(match.group(2))
            else:   # Last resort, try the config values
                lat = loc_conf.get("Latitude")
                lon = loc_conf.get("Longitude")

        if lat is None or lon is None:
            self.logger.log_message("Latitude and longitude could not be determined, using defaults for 0°00'00\"N 0°00'00.0\"E.", "warning")
            tz = tz or "UTC"
            lat = 0.0
            lon = 0.0

        astral_info = DateHelper.get_dawn_dusk_times(latitude=lat, longitude=lon, timezone=tz)   # Issue 80

        return_obj = {
            "dawn": astral_info["dawn"].time(),
            "dusk": astral_info["dusk"].time(),
        }
        return return_obj
