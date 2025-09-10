"""Take any object and serialises it to a json file, converting data types as needed."""
import copy
import datetime as dt
import json
import re
from pathlib import Path

from dateutil.parser import parse


class JSONEncoder:
    """Class to handle encoding and decoding of JSON data with special handling for date and datetime objects."""
    @staticmethod
    def serialise_to_json(data) -> str:
        """Serialises the data to a JSON string, converting as needed.

        Raises:
            RuntimeError: If the data cannot be serialized.

        Returns:
            str: The JSON string representation of the data.
        """
        try:
            save_data = copy.deepcopy(data)
            save_data = JSONEncoder._add_datatype_hints(save_data)
            json_string = json.dumps(save_data, indent=4, default=JSONEncoder._encode_object)
        except (TypeError, ValueError) as e:
            raise RuntimeError from e
        else:
            return json_string

    @staticmethod
    def deserialise_from_json(json_string: str):
        """Deserialises the JSON string to an object, converting as needed.

        Raises:
            RuntimeError: If the data cannot be deserialized.

        Returns:
            The deserialized object.
        """
        try:
            json_data = json.loads(json_string)
            return_data = JSONEncoder._decode_object(json_data)
        except (json.JSONDecodeError, ValueError) as e:
            raise RuntimeError from e
        else:
            return return_data

    @staticmethod
    def save_to_file(data, file_path: Path) -> bool:
        """Saves the date to a JSON file, converting as needed.

        Raises:
            RuntimeError: If the data cannot be serialized.

        Returns:
            result (bool): True if the pricing data was saved, False if not.
        """
        try:
            with file_path.open("w", encoding="utf-8") as json_file:
                save_data = copy.deepcopy(data)
                save_data = JSONEncoder._add_datatype_hints(save_data)
                json.dump(save_data, json_file, indent=4, default=JSONEncoder._encode_object)
        except (TypeError, ValueError, OSError) as e:
            raise RuntimeError from e
        return True

    @staticmethod
    def read_from_file(file_path: Path) -> object | None:
        """Reads the JSON data from a file and decodes it.

        Args:
            file_path (Path): The path to the JSON file.

        Raises:
            RuntimeError: If the data cannot be read or decoded.

        Returns:
            dict: The decoded JSON data.
        """
        if not file_path.exists():
            return None

        try:
            with file_path.open("r", encoding="utf-8") as json_file:
                json_data = json.load(json_file)
                return_data = JSONEncoder._decode_object(json_data)
                return return_data
        except (json.JSONDecodeError, OSError) as e:
            raise RuntimeError from e

    @staticmethod
    def _add_datatype_hints(obj):
        """Add datetime hints to the object before it's serialized.

        Args:
            obj: The object to convert.

        Returns:
            The object with hints added
        """
        if isinstance(obj, dict):
            # iterate over a static list of items so we can safely add new keys
            for k, v in list(obj.items()):
                if isinstance(v, (dt.date, dt.datetime, dt.time)):
                    obj[f"{k}__datatype"] = type(v).__name__  # e.g. "date", "datetime", "time"
                elif isinstance(v, (dict, list)):
                    obj[k] = JSONEncoder._add_datatype_hints(v)
        elif isinstance(obj, list):
            return [JSONEncoder._add_datatype_hints(item) for item in obj]
        return obj

    @staticmethod
    def _encode_object(obj):
        """Convert the object to JSON serialisable format if it's a date or datetime. This function is use by json.dump().

        Args:
            obj: The object to convert.

        Raises:
            TypeError: If the object is not serializable.

        Returns:
            The JSON serializable representation of the object.
        """
        if isinstance(obj, (dt.datetime, dt.date, dt.time)):
            return obj.isoformat()
        error_msg = f"Type {type(obj)} not serializable"
        raise TypeError(error_msg)

    @staticmethod
    def _decode_object(obj):  # noqa: PLR0912
        """Convert the JSON object back to its original form, including date and datetime objects.

        Args:
            obj: The JSON object to convert.

        Returns:
            The original object.
        """
        if isinstance(obj, dict):
            for k, v in list(obj.items()):
                if isinstance(v, str):
                    # See if there's a datatype hint for this key
                    datatype_hint = obj.get(f"{k}__datatype")

                    # remove the datatype hint from the object
                    obj.pop(f"{k}__datatype", None)
                    if datatype_hint == "date":
                        try:
                            obj[k] = dt.date.fromisoformat(v)
                            continue
                        except ValueError:
                            pass
                    elif datatype_hint == "datetime":
                        try:
                            obj[k] = dt.datetime.fromisoformat(v)
                            continue
                        except ValueError:
                            pass
                    elif datatype_hint == "time":
                        try:
                            obj[k] = dt.time.fromisoformat(v)
                            continue
                        except ValueError:
                            pass

                    # If the string is a date-only value like "YYYY-MM-DD", decode to a date
                    if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
                        try:
                            obj[k] = dt.time.fromisoformat(v)
                            continue
                        except ValueError:
                            # fall through to the full parse attempt
                            pass

                    try:
                        dt_obj = parse(v)
                        # If time part is zero, treat as date
                        if dt_obj.time() == dt.time(0, 0):
                            obj[k] = dt_obj.date()
                        else:
                            obj[k] = dt_obj
                    except ValueError:
                        pass    # Just ignore
                elif isinstance(v, (dict, list)):
                    obj[k] = JSONEncoder._decode_object(v)
        elif isinstance(obj, list):
            return [JSONEncoder._decode_object(item) for item in obj]
        return obj
