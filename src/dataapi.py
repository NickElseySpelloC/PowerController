"""DataAPI servicing module for PowerController.

This model responds to API requests with the latest data from the system, which is refreshed on demand or at regular intervals.
It provides a structured way to access the current state of outputs and other relevant information for external clients.
"""
import os

from sc_utility import SCConfigManager, SCLogger

from controller import PowerController


def _validate_access_key(config: SCConfigManager, logger: SCLogger, key_from_request: str | None) -> bool:
    expected_key = os.environ.get("DATAAPI_ACCESS_KEY")
    if not expected_key:
        expected_key = config.get("DataAPI", "AccessKey")
    if expected_key is None:
        return True
    if isinstance(expected_key, str) and not expected_key.strip():
        # Current behavior: empty AccessKey means open access.
        return True

    if key_from_request is None:
        logger.log_message("Missing access key.", "warning")
        return False
    key = key_from_request.strip()
    if not key:
        logger.log_message("Blank access key used.", "warning")
        return False
    if key != expected_key:
        logger.log_message("Invalid access key used.", "warning")
        return False
    return True
