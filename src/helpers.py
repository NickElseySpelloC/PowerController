"""General helper functions"""
import csv
from pathlib import Path

from sc_foundation import SCConfigManager

from local_enumerations import (
    DEFAULT_CURRENCY_SYMBOL,
    DEFAULT_CURRENCY_SUBUNIT_SYMBOL,
)

def get_currency_symbols(config: SCConfigManager) -> tuple[str, str]:
    """Get the major and minor currency symbols from the config file or failing that use the defaults.

    Args:
        config (SCConfigManager): The configuration manager for the system.

    Returns:
        tuple[str, str]: A tuple containing the major and minor currency symbols.
    """
    major = config.get("General", "CurrencySymbol", default=DEFAULT_CURRENCY_SYMBOL) or DEFAULT_CURRENCY_SYMBOL
    minor = config.get("General", "CurrencySubunitSymbol", default=DEFAULT_CURRENCY_SUBUNIT_SYMBOL) or DEFAULT_CURRENCY_SUBUNIT_SYMBOL
    
    return major, minor  # pyright: ignore[reportReturnType]


class DebugSupport:
    @staticmethod
    def dump_list_to_csv(file_name: str, list_obj: list[dict]) -> None:
        """
        Dump a list object to a CSV file for debugging.

        Args:
            file_name (str): The name of the CSV file to create.
            list_obj(list[dict]): The data to dump.
        """
        file_path = Path(file_name)

        # If no data, delete the existing file if there
        if not list_obj:
            if file_path.exists():
                file_path.unlink()
            return

        with file_path.open("w", newline="", encoding="utf-8") as csvfile:
            fieldnames = list_obj[0].keys()
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for item in list_obj:
                writer.writerow(item)
