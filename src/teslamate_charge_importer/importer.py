from __future__ import annotations

from typing import TYPE_CHECKING

from .models import EnergyBucket, TeslaImportResult

if TYPE_CHECKING:
    from datetime import date

    from .db import TeslaMateDb


def import_charging_buckets(db: TeslaMateDb, start_date: date, geofence_name: str | None = None, convert_to_local: bool = True) -> TeslaImportResult:
    try:
        sessions = db.get_sessions_since(start_date, geofence_name=geofence_name, convert_to_local=convert_to_local)
        raw = db.get_5min_buckets_since(start_date, geofence_name=geofence_name, convert_to_local=convert_to_local)
    except (ConnectionError) as e:
        raise ConnectionError(e) from e
    else:
        buckets: list[EnergyBucket] = []
        for session_id, bucket_start, bucket_end, kwh_added in raw:
            # avg kW over 5 minutes = kWh * 12
            avg_kw = (kwh_added * 12.0)
            buckets.append(
                EnergyBucket(
                    charging_process_id=session_id,
                    bucket_start=bucket_start,
                    bucket_end=bucket_end,
                    kwh_added=kwh_added,
                    avg_kw=avg_kw,
                )
            )

        return TeslaImportResult(
            start_date=db._start_ts_from_date(start_date),  # type: ignore[attr-defined]  # noqa: SLF001
            sessions=sessions,
            buckets=buckets,
        )
