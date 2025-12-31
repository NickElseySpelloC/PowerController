"""Outputs JSON lines by default (easy to ingest). Also supports --write-state to update your “last run date”."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from teslamate_charge_importer.config import DbConfig
from teslamate_charge_importer.db import TeslaMateDb
from teslamate_charge_importer.importer import import_charging_buckets

if TYPE_CHECKING:
    from sc_utility import SCConfigManager

    from teslamate_charge_importer.models import TeslaImportResult


def print_charging_data(config: SCConfigManager, start_date: dt.date) -> None:
    """Print charging sessions and buckets from TeslaMate as JSON lines.

    Args:
        config: The SCConfigManager instance with TeslaMate config.
        start_date: The date from which to start importing charging data.

    Raises:
        ConnectionError: If unable to connect to the TeslaMate database.
    """
    cfg = DbConfig(config)
    if not cfg.enabled:
        return  # Skip if not enabled
    db = TeslaMateDb(cfg)

    try:
        result = import_charging_buckets(db, start_date=start_date, geofence_name=cfg.geofence_name)
    except ConnectionError as e:
        raise ConnectionError(e) from e
    else:
        # Default: print both if neither specified
        show_sessions = True
        show_buckets = True

        if show_sessions:
            for s in result.sessions:
                print(
                    json.dumps(
                        {
                            "type": "session",
                            "id": s.id,
                            "car_id": s.car_id,
                            "start_date": s.start_date.isoformat(sep=" "),
                            "end_date": s.end_date.isoformat(sep=" ") if s.end_date else None,
                            "duration_min": s.duration_min,
                            "start_battery_level": s.start_battery_level,
                            "end_battery_level": s.end_battery_level,
                            "charge_energy_added_kwh": float(s.charge_energy_added_kwh) if s.charge_energy_added_kwh else None,
                            "charge_energy_used_kwh": float(s.charge_energy_used_kwh) if s.charge_energy_used_kwh else None,
                            "cost": float(s.cost) if s.cost else None,
                            "geofence_name": s.geofence_name,
                            "short_address": s.short_address,
                        }
                    )
                )

        if show_buckets:
            for b in result.buckets:
                print(
                    json.dumps(
                        {
                            "type": "bucket",
                            "session_id": b.charging_process_id,
                            "bucket_start": b.bucket_start.isoformat(sep=" "),
                            "bucket_end": b.bucket_end.isoformat(sep=" "),
                            "kwh_added": float(b.kwh_added),
                            "avg_kw": float(b.avg_kw),
                        }
                    )
                )


def get_charging_data(config: SCConfigManager, start_date: dt.date) -> TeslaImportResult | None:
    """Return the charging data as a TeslaImportResult object.

    Args:
        config: The SCConfigManager instance with TeslaMate config.
        start_date: The date from which to start importing charging data.

    Raises:
        ConnectionError: If unable to connect to the TeslaMate database.

    Returns:
        TeslaImportResult | None: The imported charging data, or None if not enabled.
    """
    cfg = DbConfig(config)
    if not cfg.enabled:
        return None  # Skip if not enabled
    db = TeslaMateDb(cfg)

    try:
        result = import_charging_buckets(db, start_date=start_date, geofence_name=cfg.geofence_name)
    except ConnectionError as e:
        raise ConnectionError(e) from e
    else:
        return result


def get_charging_data_as_dict(config: SCConfigManager, start_date: dt.date) -> dict | None:
    """Return the charging data as a dict.

    Args:
        config: The SCConfigManager instance with TeslaMate config.
        start_date: The date from which to start importing charging data.

    Raises:
        ConnectionError: If unable to connect to the TeslaMate database.

    Returns:
        dict | None: The imported charging data, or None if not enabled.
    """
    cfg = DbConfig(config)
    if not cfg.enabled:
        return None  # Skip if not enabled
    db = TeslaMateDb(cfg)

    try:
        result = import_charging_buckets(db, start_date=start_date, geofence_name=cfg.geofence_name)
    except ConnectionError as e:
        raise ConnectionError(e) from e
    else:
        return_dict = {
            "start_date": result.start_date.isoformat(),
            "sessions": [asdict(s) for s in result.sessions],
            "buckets": [asdict(b) for b in result.buckets],
        }
        return return_dict


def merge_session_dict_records(existing_sessions: list[dict], new_sessions: list[dict]) -> list[dict]:
    # Merge sessions by session id (replace existing, append new)

    existing_list = [x for x in (existing_sessions or []) if isinstance(x, dict)]
    incoming_list = [x for x in (new_sessions or []) if isinstance(x, dict)]
    id_keys = ("id", "session_id")

    def _get_id(item: dict[str, Any]) -> str | None:
        for key in id_keys:
            if key in item and item[key] is not None:
                return str(item[key])
        return None

    merged: list[dict[str, Any]] = []
    id_to_index: dict[str, int] = {}

    # Seed with existing items (keep order)
    for item in existing_list:
        item_id = _get_id(item)
        merged.append(dict(item))
        if item_id is not None and item_id not in id_to_index:
            id_to_index[item_id] = len(merged) - 1

    # Apply incoming items (replace or append)
    for item in incoming_list:
        item_id = _get_id(item)
        if item_id is None:
            merged.append(dict(item))
            continue

        if item_id in id_to_index:
            merged[id_to_index[item_id]] = dict(item)
        else:
            id_to_index[item_id] = len(merged)
            merged.append(dict(item))

    return merged


def merge_bucket_dict_records(existing_buckets: list[dict], new_buckets: list[dict], start_date: dt.date) -> list[dict]:
    # Merge buckets by (session_id, bucket_start) tuple (replace existing, append new)

    pruned_existing_buckets: list[dict[str, Any]] = []
    for b in existing_buckets:
        if not isinstance(b, dict):
            continue
        bucket_date = b.get("bucket_start").date()  # pyright: ignore[reportOptionalMemberAccess]

        # If we can't determine a date, keep the record rather than risk deleting valid data.
        if start_date and bucket_date and bucket_date >= start_date:
            continue

        pruned_existing_buckets.append(b)

    # Merge: remaining existing buckets + all new buckets
    merged_buckets: list[dict[str, Any]] = pruned_existing_buckets + [
        x for x in new_buckets if isinstance(x, dict)
    ]

    def _bucket_sort_key(item: dict[str, Any]) -> tuple[int, str]:
        cpid_val = item.get("charging_process_id")
        try:
            cpid_int = int(cpid_val)  # pyright: ignore[reportArgumentType]
        except (TypeError, ValueError):
            cpid_int = 2**31 - 1

        bucket_start_val = item.get("bucket_start", item.get("BucketStart"))
        if isinstance(bucket_start_val, (dt.datetime, dt.date)):
            bucket_start_str = bucket_start_val.isoformat()
        elif bucket_start_val is None:
            bucket_start_str = ""
        else:
            bucket_start_str = str(bucket_start_val)

        return (cpid_int, bucket_start_str)

    merged_buckets.sort(key=_bucket_sort_key)
    return merged_buckets
