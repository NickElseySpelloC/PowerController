"""Outputs JSON lines by default (easy to ingest). Also supports --write-state to update your “last run date”."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from teslamate_charge_importer.config import DbConfig
from teslamate_charge_importer.db import TeslaMateDb
from teslamate_charge_importer.importer import import_charging_buckets

if TYPE_CHECKING:
    from datetime import date
    from decimal import Decimal

    from sc_utility import SCConfigManager

    from teslamate_charge_importer.models import TeslaImportResult


def _dec(v: Decimal) -> str:
    return format(v, "f")


def print_charging_data(config: SCConfigManager, start_date: date) -> None:
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
                            "charge_energy_added_kwh": _dec(s.charge_energy_added_kwh) if s.charge_energy_added_kwh else None,
                            "charge_energy_used_kwh": _dec(s.charge_energy_used_kwh) if s.charge_energy_used_kwh else None,
                            "cost": _dec(s.cost) if s.cost else None,
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
                            "kwh_added": _dec(b.kwh_added),
                            "avg_kw": _dec(b.avg_kw),
                        }
                    )
                )


def get_charging_data(config: SCConfigManager, start_date: date) -> TeslaImportResult | None:
    """Return the charging data as a dict.

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
