"""Support functions for integration with external services."""

import gzip
import json
import os

import requests
from sc_utility import DateHelper, JSONEncoder, SCConfigManager, SCLogger

HTTP_STATUS_FORBIDDEN = 403


class ExternalServiceHelper:
    """Support functions for integration with external services."""

    def __init__(self, config: SCConfigManager, logger: SCLogger):
        """Initialize the ExternalServiceHelper with a configuration and logger.

        Args:
            config (SCConfigManager): The configuration dictionary containing device settings.
            logger (SCLogger): An instance of a logger to log messages.
        """
        self.config = config
        self.logger = logger
        self.heartbeat_last_post = None

    def ping_heatbeat(self, is_fail: bool | None = None) -> bool:
        """Ping the heartbeat URL to check if the service is available.

        Args:
            is_fail (bool, optional): If True, the heartbeat will be considered a failure.

        Returns:
            bool: True if the heartbeat URL is reachable, False otherwise.
        """
        is_enabled = self.config.get("HeartbeatMonitor", "Enable", default=False)
        heartbeat_url = self.config.get("HeartbeatMonitor", "WebsiteURL")
        timeout = self.config.get("HeartbeatMonitor", "HeartbeatTimeout", default=10)
        frequency = self.config.get("HeartbeatMonitor", "Frequency", default=30)

        if not is_enabled or heartbeat_url is None:
            return True
        assert isinstance(heartbeat_url, str), "Heartbeat URL must be a string"

        if self.heartbeat_last_post is not None:
            time_since_last_post = (DateHelper.now() - self.heartbeat_last_post).total_seconds()
            if time_since_last_post < frequency:  # pyright: ignore[reportOperatorIssue]
                return True

        if is_fail:
            heartbeat_url += "/fail"

        try:
            response = requests.get(heartbeat_url, timeout=timeout)  # type: ignore[call-arg]
        except requests.exceptions.Timeout as e:
            self.logger.log_message(f"Timeout making Heartbeat ping: {e}", "error")
            return False
        except requests.RequestException as e:
            self.logger.log_message(f"Heartbeat ping failed: {e}", "error")
            return False
        else:
            if response.status_code == 200:
                # self.logger.log_message(f"Heartbeat ping posted to {heartbeat_url}", "debug")
                return True
            self.logger.log_message(f"Heartbeat ping failed with status code: {response.status_code}", "error")
            return False

    def post_state_to_web_viewer(self, system_state: dict) -> None:
        """Post the state to the web server if WebsiteBaseURL is set in config.

        Args:
            system_state (dict): The state data to be posted, json friendly
        """
        is_enabled = self.config.get("ViewerWebsite", "Enable", default=False)
        base_url = self.config.get("ViewerWebsite", "BaseURL", default=None)
        access_key = os.environ.get("VIEWER_ACCESS_KEY")
        if not access_key:
            access_key = self.config.get("ViewerWebsite", "AccessKey", default=None)
        timeout_wait = self.config.get("ViewerWebsite", "APITimeout", default=5)

        if not is_enabled or base_url is None:
            return

        # Convert the system state to a JSON-ready dict
        if not isinstance(system_state, (dict, list)):
            self.logger.log_fatal_error("System state must be a dict or list to post to web viewer.")
            return
        try:
            json_data = JSONEncoder.ready_dict_for_json(system_state)
            json_str = json.dumps(json_data)
            compressed_data = gzip.compress(json_str.encode("utf-8"))
        except RuntimeError as e:
            self.logger.log_fatal_error(f"Failed to prepare system state for JSON: {e}")

        api_url = base_url + "/api/submit"  # pyright: ignore[reportOperatorIssue]
        if access_key:
            api_url += f"?key={access_key}"
        headers = {
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
        }
        try:
            response = None
            response = requests.post(api_url, headers=headers, data=compressed_data, timeout=timeout_wait)  # type: ignore[call-arg]
            assert isinstance(response, requests.Response)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            try:
                returned_json = response.json()  # pyright: ignore[reportOptionalMemberAccess, reportPossiblyUnboundVariable]
            except (ValueError, requests.exceptions.JSONDecodeError):
                returned_json = response.text if hasattr(response, "text") else "No response content"  # pyright: ignore[reportOptionalMemberAccess, reportPossiblyUnboundVariable]
            if response.status_code == HTTP_STATUS_FORBIDDEN:  # pyright: ignore[reportOptionalMemberAccess, reportPossiblyUnboundVariable]
                self.logger.log_message(f"Access denied ({HTTP_STATUS_FORBIDDEN} Forbidden) when posting to {api_url}. Check your access key or permissions. Error: {e}, Response: {returned_json}", "error")
            else:
                self.logger.log_message(f"HTTP error saving state to web server at {api_url}: Error: {e}, Response: {returned_json}", "warning")
        except requests.exceptions.ConnectionError as e:
            self.logger.log_message(f"Web server at {api_url} is unavailable. Error: {e}", "warning")
        except requests.exceptions.Timeout as e:
            self.logger.log_message(f"Timeout while trying to save state to web server at {api_url}: Error: {e}", "warning")
        except requests.exceptions.RequestException as e:
            if not response:
                self.logger.log_fatal_error(f"Unknown error saving state to web server at {api_url}: Error: {e}, No response received.")
            try:
                returned_json = response.json()  # pyright: ignore[reportOptionalMemberAccess, reportPossiblyUnboundVariable]
            except (ValueError, requests.exceptions.JSONDecodeError, UnboundLocalError):
                returned_json = response.text if hasattr(response, "text") else "No response content"  # pyright: ignore[reportOptionalMemberAccess, reportPossiblyUnboundVariable]
            self.logger.log_fatal_error(f"Error saving state to web server at {api_url}: Error: {e}, Response: {returned_json}")
        else:
            # Record the time of the last post even if it failed so that we don't keep retrying on errors
            # self.logger.log_message(f"Posted state for {system_state.get('DeviceName')} to {api_url}.", "debug")
            pass
