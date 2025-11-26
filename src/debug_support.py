"""General helper functions for debugging."""
import csv
from pathlib import Path


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
