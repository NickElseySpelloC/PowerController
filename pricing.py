"""The pricing module that manages the interface to Amber and determines when to run based on the best pricing strategy."""
import datetime as dt
import operator
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from sc_utility import DateHelper, SCCommon, SCConfigManager, SCLogger

from enumerations import (
    PRICE_SLOT_INTERVAL,
    PRICES_DATA_FILE,
    AmberAPIMode,
    AmberChannel,
    PriceFetchMode,
    RunPlanMode,
)
from json_encoder import JSONEncoder
from run_plan import RunPlanner


class PricingManager:
    def __init__(self, config: SCConfigManager, logger: SCLogger):
        """Initializes the PricingManager.

        Args:
            config (SCConfigManager): The configuration manager for the system.
            logger (SCLogger): The logger for the system.
        """
        self.config = config
        self.logger = logger
        self.next_refresh = DateHelper.now()

        # Amber specific information
        self.mode = self.config.get("AmberAPI", "Mode", default=AmberAPIMode.LIVE)
        self.site_id = None
        self.timeout = self.config.get("AmberAPI", "Timeout", default=10)
        self.concurrent_error_count = 0
        self.raw_price_data = []   # The raw pricing data retrieved from Amber
        self.price_data = []       # The processed pricing data

        self.base_url = self.config.get("AmberAPI", "APIURL")
        self.api_key = self.config.get("AmberAPI", "APIKey")
        if not self.base_url or not self.api_key:
            if self.mode != AmberAPIMode.DISABLED:
                self.logger.log_message("Amber API is not properly configured, disabling Amber pricing.", "error")
            self.mode = AmberAPIMode.DISABLED
            return

        self.refresh_price_data()

    def refresh_price_data_if_time(self) -> bool:
        """Refresh the pricing data if the refresh interval has passed.

        Returns:
            result(bool): True if the refresh was successful or AmberPricing disabled, False if there was an error.
        """
        if DateHelper.now() >= self.next_refresh:
            self.refresh_price_data()
            return True
        return False

    def refresh_price_data(self) -> bool:
        """Refreshes the pricing data from Amber.

        Returns:
            result(bool): True if the refresh was successful or AmberPricing disabled, False if there was an error.
        """
        if self.mode == AmberAPIMode.DISABLED:
            return True

        if not self._refresh_amber_prices():
            return False
        assert isinstance(self.raw_price_data, list)

        # Now build the self.raw_price_data list into 5 minute increments for today
        today = DateHelper.today()
        now = DateHelper.now().replace(tzinfo=None)
        # Round down to the nearest 5 minutes
        rounded_minute = now.minute - (now.minute % PRICE_SLOT_INTERVAL)
        first_start_time = now.replace(minute=rounded_minute, second=0, microsecond=0)
        for channel in self.raw_price_data:

            channel_data = {
                "Name": channel["Name"],
                "PriceData": []
            }

            for entry in channel["PriceData"]:
                start_time = entry["StartDateTime"]
                end_time = entry["EndDateTime"]
                if end_time >= first_start_time and start_time.date() == today:
                    while start_time < end_time and start_time.date() == today:
                        if start_time >= first_start_time:
                            slot_end_time = start_time + dt.timedelta(minutes=PRICE_SLOT_INTERVAL)
                            channel_data["PriceData"].append({
                                "Date": start_time.date(),
                                "StartTime": start_time.time(),
                                "StartDateTime": start_time,
                                "EndTime": slot_end_time.time(),
                                "EndDateTime": slot_end_time,
                                "Minutes": PRICE_SLOT_INTERVAL,
                                "Price": entry["Price"]
                            })
                        start_time += dt.timedelta(minutes=PRICE_SLOT_INTERVAL)

            self.price_data.append(channel_data)

        # Finally create a best price sorted version of each channel's data
        for channel in self.price_data:
            channel["SortedPriceData"] = sorted(channel["PriceData"], key=operator.itemgetter("Price"))

        return True

    def _refresh_amber_prices(self) -> bool:
        """Retrieves the current raw pricing data from Amber.

        Returns:
            result(bool): True if the refresh was successful or AmberPricing disabled, False if there was an error.
        """
        connection_error = False
        refresh_interval = self.config.get("AmberAPI", "RefreshInterval", default=5)
        # If Amber pricing is disabled, nothing to do
        if self.mode == AmberAPIMode.DISABLED:
            self.next_refresh = DateHelper.now() + dt.timedelta(minutes=refresh_interval)  # pyright: ignore[reportArgumentType]
            return True
        if self.mode == AmberAPIMode.LIVE:
            # Maximum number of API query errors before we exit the app
            max_errors = self.config.get("AmberAPI", "MaxConcurrentErrors", default=10)

            # By default, our next refresh is 5 mins from now
            self.next_refresh = DateHelper.now() + dt.timedelta(minutes=refresh_interval)  # pyright: ignore[reportArgumentType]

            # Authenticate to Amber
            assert isinstance(self.raw_price_data, list)
            while True:
                if not self._amber_authenticate():
                    connection_error = True
                    break
                # We authenticated to Amber, so go get the default pricing data
                self.raw_price_data.clear()  # Clear the list
                result = self._get_amber_data(interval_window=5, num_intervals=72)  # Get two hours of 5 minute data (up to 3 channels)
                if not result:
                    connection_error = True
                    break
                channel_list, short_term_data = result
                result = self._get_amber_data(interval_window=30, num_intervals=290)  # Get at least 48 hours of 30 minute data (up to 3 channels)
                if not result:
                    connection_error = True
                    break
                _, long_term_data = result

                # Consolidate the two data sets
                for channel in channel_list:
                    channel_data = {
                        "Name": channel,
                        "PriceData": []
                        }

                    # Add the short term data first
                    for entry in short_term_data:
                        if entry.get("Channel") == channel:
                            entry.pop("Channel", None)  # Remove the channel key
                            channel_data["PriceData"].append(entry)

                    # Now add the long term data, but only if it doesn't overlap with the short term data
                    for entry in long_term_data:
                        if entry.get("Channel") == channel and entry["StartDateTime"] >= channel_data["PriceData"][-1]["EndDateTime"]:
                            entry.pop("Channel", None)  # Remove the channel key
                            channel_data["PriceData"].append(entry)
                    self.raw_price_data.append(channel_data)

                # And finally save the lot to file
                self._save_prices()
                self.next_refresh = DateHelper.now() + dt.timedelta(minutes=refresh_interval)  # pyright: ignore[reportArgumentType]
                self.logger.log_message(f"Refreshed Amber pricing. Next refresh at {self.next_refresh.strftime('%H:%M:%S')}", "debug")
                break

        # If we get here but there was a connection error along the way
        if connection_error:
            if max_errors and self.concurrent_error_count >= max_errors:  # pyright: ignore[reportOperatorIssue]
                self.logger.log_fatal_error("Max concurrent errors reached quering Amber API, exiting.")
                return False
            self.next_refresh = DateHelper.now() + dt.timedelta(minutes=1)  # Shorten the refresh interval if we previously errored
            self.logger.log_message(f"Amber unavailable, reverting to default pricing / schedules. Next attempt at {self.next_refresh.strftime('%H:%M:%S')}", "warning")

        if connection_error or self.mode == AmberAPIMode.OFFLINE:
            # If we had an error but still within limits, revert to default pricing
            self.next_refresh = DateHelper.now() + dt.timedelta(minutes=1)  # Shorten the refresh interval if we previously errored
            self._import_prices()

        return True

    def _amber_authenticate(self) -> bool:
        """Login to Amber and get the site ID.

        Returns:
            result (bool): True if the site ID was retrieved, False if Amber unreachable.
        """
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        try:
            url = self.base_url + "/sites"  # type: ignore[attr-defined]

            response = requests.get(f"{url}", headers=headers, timeout=self.timeout)  # type: ignore[attr-defined]
            response.raise_for_status()
            sites = response.json()
            for site in sites:
                if site.get("status") == "active":
                    self.api_error_count = 0
                    self.site_id = site.get("id")
                    self.concurrent_error_count = 0  # reset the error count
                    return True

            self.logger.log_fatal_error("No active Amber sites found.")

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:  # Trap connection and timeout errors
            self.logger.log_message(f"Connection error or timeout while authenticating to Amber: {e}", "warning")
            return False

        except requests.exceptions.RequestException as e:
            self.logger.log_message(f"Error fetching Amber site ID: {e}", "error")
            self.concurrent_error_count += 1
            return False
        else:
            return False

        return True

    def get_next_refresh(self) -> dt.datetime:
        """Determines when to next refresh the pricing data.

        Returns:
            dt.datetime: When to next call the refresh_pricing function.
        """
        return self.next_refresh  # pyright: ignore[reportReturnType]

    def _get_amber_data(self, interval_window: int, num_intervals: int) -> tuple[list, list[dict]] | None:
        """Gets the raw pricing data from Amber for a given number of intervals.

        Cleans up the raw data provided by Amber and returns the processed data.

        Returns:
            channel_list (list[str]): The list of channels to fetch data for.
            price_data (list[dict]): The requested pricing data, or None if there was an issue
        """
        if not self.site_id:
            self.logger.log_fatal_error("Functional called before Amber authentication.", report_stack=True)
        if interval_window not in {5, 30} or num_intervals <= 0 or num_intervals > 2048:
            self.logger.log_fatal_error("Invalid parameters.", report_stack=True)

        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        url = f"{self.base_url}/sites/{self.site_id}/prices/current?next={num_intervals}&previous=0&resolution={interval_window}"

        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)  # type: ignore[attr-defined]
            response.raise_for_status()
            response_data = response.json()

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:  # Trap connection and timeout errors
            self.logger.log_message(f"Connection error or timeout while authenticating to Amber: {e}", "warning")
            return None

        except requests.exceptions.RequestException as e:
            self.logger.log_message(f"Error fetching Amber prices: {e}", "error")
            self.concurrent_error_count += 1
            return None

        self.concurrent_error_count = 0  # reset the error count
        # Extract just the key/value pairs we care about
        price_data = []
        channel_list = []
        for entry in response_data:
            dt_start = self._convert_utc_dt_string(entry["startTime"])
            dt_end = self._convert_utc_dt_string(entry["endTime"])
            new_entry = {
                "Date": dt_start.date(),
                "Channel": entry["channelType"],
                "StartTime": dt_start.time(),
                "StartDateTime": dt_start,
                "EndTime": dt_end.time(),
                "EndDateTime": dt_end,
                "Minutes": int(entry["duration"]),  # Duration of this slot in minutes
                "Price": float(entry["perKwh"]),
            }
            price_data.append(new_entry)
            if entry["channelType"] not in channel_list:
                channel_list.append(entry["channelType"])

        return channel_list, price_data

    def _save_prices(self) -> bool:
        """Saves the raw pricing data to disk.

        Returns:
            result (bool): True if the pricing data was saved, False if not.
        """
        file_path = SCCommon.select_file_location(PRICES_DATA_FILE)
        assert isinstance(file_path, Path)
        try:
            return JSONEncoder.save_to_file(self.raw_price_data, file_path)
        except RuntimeError as e:
            self.logger.log_message(f"Error saving raw price data file {file_path}: {e}", "error")
            return False

    def _import_prices(self) -> bool:
        """Loads the default pricing data from disk if available.

        Returns:
            result (bool): True if the pricing data was loaded, False if not.
        """
        file_path = SCCommon.select_file_location(PRICES_DATA_FILE)
        assert isinstance(file_path, Path)
        assert isinstance(self.raw_price_data, list)
        if not file_path.exists():
            return False
        self.raw_price_data.clear()

        def is_date_only(x):
            return isinstance(x, dt.date) and not isinstance(x, dt.datetime)

        try:
            self.raw_price_data = JSONEncoder.read_from_file(file_path)
            assert isinstance(self.raw_price_data, list)
            # Make sure the StartDateTime and EndDateTime keys are actual dt.datetime objects
            for channel in self.raw_price_data:
                for entry in channel["PriceData"]:
                    if is_date_only(entry["StartDateTime"]):
                        entry["StartDateTime"] = dt.datetime.combine(entry["StartDateTime"], dt.time.min)
                    if is_date_only(entry["EndDateTime"]):
                        entry["EndDateTime"] = dt.datetime.combine(entry["EndDateTime"], dt.time.min)
        except RuntimeError as e:
            self.logger.log_message(f"Error importing raw price data file {file_path}: {e}", "error")
            return False
        else:
            return True

    def is_channel_valid(self, channel_id: AmberChannel) -> bool:
        """Checks if the specified channel ID is valid.

        Args:
            channel_id (AmberChannel): The ID of the channel to check.

        Returns:
            is_valid (bool): True if the channel ID is valid, False otherwise.
        """
        if channel_id is None:
            return False
        return any(channel["Name"] == channel_id for channel in self.price_data)

    def _get_channel_prices(self, channel_id: AmberChannel = AmberChannel.GENERAL, which_type: PriceFetchMode = PriceFetchMode.NORMAL) -> list[dict]:
        """Returns the list of prices for the specified channel.

        Args:
            channel_id (AmberChannel): The ID of the channel to get the prices for.
            which_type (PriceFetchMode): The type of prices to get (normal or sorted).

        Returns:
            prices (list[float]): A list of prices in AUD/kWh for the specified channel, or an empty list if invalid.
        """
        if not self.is_channel_valid(channel_id):
            self.logger.log_message(f"Invalid channel ID '{channel_id}' specified when getting channel prices.", "error")
            return []
        if which_type not in PriceFetchMode:
            self.logger.log_message(f"Invalid price type '{which_type}' specified when getting channel prices.", "error")
            return []

        for channel in self.price_data:
            if channel["Name"] == channel_id:
                if which_type == PriceFetchMode.SORTED:
                    return channel["SortedPriceData"]
                return channel["PriceData"]
        return []

    def get_available_time(self, channel_id: AmberChannel = AmberChannel.GENERAL) -> float:
        """Returns the number of hours of price data available for the selected channel.

        Args:
            channel_id (str | None): The ID of the channel to get the price data for.

        Returns:
            duration (float): The duration of price data available in hours.
        """
        if not self.is_channel_valid(channel_id):
            self.logger.log_message(f"Invalid channel ID '{channel_id}' specified when checking price data duration.", "error")
            return 0.0

        start_time = DateHelper.now().replace(tzinfo=None)
        price_data = self._get_channel_prices(channel_id)
        if not price_data:
            return 0.0
        end_time = price_data[-1]["EndDateTime"]
        start_time = max(start_time, price_data[0]["StartDateTime"])
        duration = (end_time - start_time).total_seconds() / 3600.0
        return max(0.0, duration)

    def get_current_price(self, channel_id: AmberChannel = AmberChannel.GENERAL) -> float | None:
        """Fetches the current price from the Amber API.

        Args:
            channel_id (AmberChannel): The ID of the channel to get the price for.

        Returns:
            price(float): The current price in AUD/kWh, or None if channel is invalid or price data is not available.
        """
        if not self.is_channel_valid(channel_id):
            self.logger.log_message(f"Invalid channel ID '{channel_id}' specified when checking price data duration.", "error")
            return None

        price_data = self._get_channel_prices(channel_id)
        if not price_data:
            return 0.0

        return price_data[0]["Price"]

    def get_run_plan(self, required_hours: float, priority_hours: float, max_price: float, max_priority_price: float, channel_id: AmberChannel = AmberChannel.GENERAL) -> dict | None:
        """Determines when to run based on the best pricing strategy.

        Args:
            required_hours (float): The number of hours required for the task. Set to -1 to get all remaining hours that can be filled by price.
            priority_hours (float): The number of hours that should be prioritized.
            max_price (float): The maximum price to consider for the run plan.
            max_priority_price (float): The maximum price to consider for priority hours in the run plan.
            channel_id (str | None): The ID of the channel to use for pricing.

        Returns:
            plan (list[dict]): A list of dictionaries containing the run plan.
        """
        if self.mode == AmberAPIMode.DISABLED:
            return None

        try:
            # Create a run planner instance
            run_planner = RunPlanner(self.logger, RunPlanMode.BEST_PRICE, channel_id)

            sorted_price_data = self._get_channel_prices(channel_id=channel_id, which_type=PriceFetchMode.SORTED)
            run_plan = run_planner.calculate_run_plan(sorted_price_data, required_hours, priority_hours, max_price, max_priority_price)
        except RuntimeError as e:
            self.logger.log_message(f"Error occurred while calculating best price run plan: {e}", "error")
            return None
        else:
            return run_plan

    @staticmethod
    def _convert_utc_dt_string(utc_time_str: str) -> dt.datetime:
        """Converts a UTC datetime string to a local datetime string.

        Args:
            utc_time_str (str): The UTC datetime string in the format "YYYY-MM-DDTH HH:MM:SSZ"

        Returns:
            local_time_str(str): The local datetime string in ISO format without microseconds.
        """
        # Parse the string into a datetime object (with UTC timezone)
        local_tz = dt.datetime.now().astimezone().tzinfo
        utc_dt = dt.datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=ZoneInfo("UTC")).replace(tzinfo=None)

        # ZoneInfo() fails for my AEST timezone, so instead calculate the current time difference for UTC and local time
        local_timenow = dt.datetime.now(local_tz).replace(tzinfo=None)
        utc_timenow = dt.datetime.now(dt.UTC).replace(tzinfo=None)

        tz_diff = local_timenow - utc_timenow + dt.timedelta(0, 1)

        # Convert to local time and round to the nearest minute
        local_dt = utc_dt + tz_diff
        return local_dt.replace(second=0, microsecond=0).replace(tzinfo=None)
