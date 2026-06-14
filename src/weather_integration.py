"""Weather Integration module for fetching current weather data via the sc-weather library."""

import datetime as dt
import os

from sc_foundation import DateHelper, SCConfigManager, SCLogger
from sc_weather import WeatherClient
from sc_weather.models import WeatherReading

from helpers import get_location_coordinates


class WeatherIntegration:
    """Manages fetching and caching of current weather data for use in output constraints."""

    def __init__(self, config: SCConfigManager, logger: SCLogger):
        """Initialize the weather integration.

        Args:
            config (SCConfigManager): The configuration manager for the system.
            logger (SCLogger): The logger for the system.
        """
        self.config = config
        self.logger = logger
        self.enabled: bool = False
        self.refresh_interval: int = 15  # Default to 15 minutes if not specified in config
        self.provider: str = "open_meteo"
        self.time_last_polled: dt.datetime | None = None
        self.client: WeatherClient | None = None
        self.current_reading: WeatherReading | None = None

        # Initialize from config
        self.initialise()

    def initialise(self) -> None:
        """Read the config and (re)initialise the object from config.

        Creates the WeatherClient if a WeatherClient config section is present and a valid location is available.
        """
        weather_config = self.config.get("WeatherClient", default=None)
        if not weather_config:
            self.enabled = False
            self.client = None
            return

        self.refresh_interval = weather_config.get("RefreshIntervalMin", 15) or 15
        self.provider = weather_config.get("PreferredProvider", "open_meteo") or "open_meteo"

        # The OWM API key is preferentially retrieved from the OWM_API_KEY environment variable.
        api_key = os.environ.get("OWM_API_KEY") or weather_config.get("OWMAPIKey") or None

        latitude, longitude = get_location_coordinates(self.config)
        if latitude is None or longitude is None:
            self.logger.log_message("WeatherClient is configured but latitude/longitude could not be determined from the Location section. Weather constraints will be disabled.", "warning")
            self.enabled = False
            self.client = None
            return

        self.client = WeatherClient(latitude=latitude, longitude=longitude, owm_api_key=api_key)
        self.time_last_polled = None
        self.current_reading = None
        self.enabled = True

        self.logger.log_message(f"Weather integration initialised for location ({latitude}, {longitude}), preferred provider '{self.provider}', refresh every {self.refresh_interval} min.", "debug")

    def read_weather_data(self) -> None:
        """Fetch the latest weather data if the refresh interval has elapsed.

        Updates the cached current reading. Failures are logged but do not raise.
        """
        if not self.enabled or not self.client:
            return

        # See if it's time to refresh again based on the refresh interval (in minutes)
        current_time = DateHelper.now()
        if self.time_last_polled and (current_time - self.time_last_polled).total_seconds() < self.refresh_interval * 60:
            return

        self.time_last_polled = current_time

        try:
            weather_data = self.client.get_weather(first_choice=self.provider)
        except RuntimeError as e:
            self.logger.log_message(f"Failed to fetch weather data: {e}", "error")
            return

        self.current_reading = weather_data.current
        condition = self.current_reading.sky.icon_info.condition_key.value
        temperature = self.current_reading.temperature.reading
        self.logger.log_message(f"Weather updated: condition '{condition}', temperature {temperature}°C, precipitation probability {self.current_reading.precip_probability}.", "debug")

    def get_current_reading(self) -> WeatherReading | None:
        """Get the most recently fetched weather reading.

        Returns:
            WeatherReading | None: The current weather reading, or None if weather integration is disabled or no reading is available yet.
        """
        if not self.enabled:
            return None
        return self.current_reading
