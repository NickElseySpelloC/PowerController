from __future__ import annotations

import datetime as dt
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import psycopg
from psycopg.rows import tuple_row

from .models import ChargingSession

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .config import DbConfig


SESSION_QUERY = """
SELECT
  cp.id,
  cp.car_id,
  cp.start_date,
  cp.end_date,
  cp.duration_min,
  cp.start_battery_level,
  cp.end_battery_level,
  cp.charge_energy_added,
  cp.charge_energy_used,
  cp.cost,
  g.name AS geofence_name,
  concat_ws(', ', a.house_number, a.road, a.neighbourhood, a.state) AS short_address
FROM charging_processes cp
JOIN geofences g ON g.id = cp.geofence_id
LEFT JOIN addresses a ON cp.address_id = a.id
WHERE cp.start_date >= %(start_ts)s
  -- AND cp.end_date IS NOT NULL
    AND (
        NULLIF(%(geofence_name)s, '') IS NULL
        OR g.name ILIKE %(geofence_name)s
    )
ORDER BY cp.start_date ASC;
"""


# Bucketing query:
# - Filter charges by start_ts (inclusive)
# - Compute delta kWh via LAG on cumulative charge_energy_added
# - Clamp negatives to 0
# - Bucket by floor(minute/5)*5
BUCKET_QUERY = """
-- Params:
--   %(start_ts)s  = timestamp (e.g. 2025-12-01 00:00:00)

WITH in_scope_sessions AS (
  SELECT cp.id
  FROM charging_processes cp
  JOIN geofences g ON g.id = cp.geofence_id
  WHERE cp.start_date >= %(start_ts)s
    -- AND cp.end_date IS NOT NULL
    AND (
        NULLIF(%(geofence_name)s, '') IS NULL
        OR g.name ILIKE %(geofence_name)s
    )
),
samples AS (
  SELECT
    c.charging_process_id,
    c.date,
    c.charge_energy_added,
    LAG(c.charge_energy_added) OVER (
      PARTITION BY c.charging_process_id
      ORDER BY c.date
    ) AS prev_added
  FROM charges c
  JOIN in_scope_sessions s
    ON s.id = c.charging_process_id
),
deltas AS (
  SELECT
    charging_process_id,
    date,
    GREATEST(charge_energy_added - COALESCE(prev_added, charge_energy_added), 0) AS delta_kwh
  FROM samples
),
bucketed AS (
  SELECT
    charging_process_id,
    (
      date_trunc('hour', date)
      + make_interval(mins => (floor(extract(minute from date)/5)*5)::int)
    ) AS bucket_start,
    SUM(delta_kwh) AS kwh_added
  FROM deltas
  GROUP BY charging_process_id, bucket_start
)
SELECT
  charging_process_id,
  bucket_start,
  bucket_start + interval '5 minutes' AS bucket_end,
  kwh_added
FROM bucketed
ORDER BY charging_process_id, bucket_start;

"""


class TeslaMateDb:
    def __init__(self, cfg: DbConfig):
        self.cfg = cfg

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection]:
        conn = psycopg.connect(self.cfg.dsn(), row_factory=tuple_row)
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _start_ts_from_date(start_date: dt.date) -> dt.datetime:
        # TeslaMate stores timestamp without timezone; treat date as local midnight.
        local_tz = dt.datetime.now().astimezone().tzinfo
        return dt.datetime(
            start_date.year, start_date.month, start_date.day, 0, 0, 0, tzinfo=local_tz
        )

    def get_sessions_since(self,
                           start_date: dt.date,
                           geofence_name: str | None = None,
                           convert_to_local: bool = True
                          ) -> list[ChargingSession]:
        """Get charging sessions since the given date.

        Args:
            start_date: The date from which to start fetching sessions.
            geofence_name: Optional geofence name to filter sessions.
            convert_to_local: Whether to convert datetime objects to local timezone strings.

        Raises:
            ConnectionError: If unable to connect to the TeslaMate database.

        Returns:
            list[ChargingSession]: List of ChargingSession objects.
        """
        start_ts = self._start_ts_from_date(start_date)

        try:
            with self.connect() as conn, conn.cursor() as cur:
                cur.execute(
                    SESSION_QUERY,
                    {"start_ts": start_ts, "geofence_name": geofence_name},
                )
                rows = cur.fetchall()
        except (ConnectionError, psycopg.OperationalError) as e:
            error_msg = f"Could not connect to TeslaMate database: {e}"
            raise ConnectionError(error_msg) from e

        sessions: list[ChargingSession] = []
        for r in rows:
            sess_start_date = r[2]
            sess_end_date = r[3]
            if convert_to_local:
                sess_start_date = self._convert_dt_to_local(sess_start_date)
                if sess_end_date:
                    sess_end_date = self._convert_dt_to_local(sess_end_date)

            sessions.append(
                ChargingSession(
                    id=int(r[0]),
                    car_id=int(r[1]),
                    start_date=sess_start_date,
                    end_date=sess_end_date,
                    duration_min=int(r[4]) if r[4] is not None else None,
                    start_battery_level=int(r[5]) if r[5] is not None else None,
                    end_battery_level=int(r[6]) if r[6] is not None else None,
                    charge_energy_added_kwh=float(r[7]) if r[7] is not None else None,
                    charge_energy_used_kwh=float(r[8]) if r[8] is not None else None,
                    cost=r[9] if r[9] is not None else None,
                    geofence_name=r[10] if r[10] is not None else None,
                    short_address=r[11] if r[11] is not None else None,
                )
            )
        return sessions

    def get_5min_buckets_since(self,
                               start_date: dt.date,
                               geofence_name: str | None = None,
                               convert_to_local: bool = True
                          ) -> list[tuple[int, dt.datetime, dt.datetime, float]]:
        """Get 5min charging bucket records since start_date.

        Args:
            start_date: The date from which to start fetching sessions.
            geofence_name: Optional geofence name to filter sessions.
            convert_to_local: Whether to convert datetime objects to local timezone strings.

        Raises:
            ConnectionError: If unable to connect to the TeslaMate database.

        Returns:
            list: List of charging bucket objects.
        """
        start_ts = self._start_ts_from_date(start_date)

        try:
            with self.connect() as conn, conn.cursor() as cur:
                cur.execute(
                    BUCKET_QUERY, {"start_ts": start_ts, "geofence_name": geofence_name}
                )
                rows = cur.fetchall()
        except (ConnectionError, psycopg.OperationalError) as e:
            error_msg = f"Could not connect to TeslaMate database: {e}"
            raise ConnectionError(error_msg) from e

        # rows: (charging_process_id, bucket_start, bucket_end, kwh_added)
        return_rows: list[tuple[int, dt.datetime, dt.datetime, float]] = []
        for r in rows:
            charging_process_id = int(r[0])
            bucket_start = r[1]
            bucket_end = r[2]
            if convert_to_local:
                bucket_start = self._convert_dt_to_local(bucket_start)
                bucket_end = self._convert_dt_to_local(bucket_end)
            kwh_added = float(r[3]) or float(0)

            return_rows.append(
                (charging_process_id, bucket_start, bucket_end, kwh_added)
            )
        return return_rows

    def _convert_dt_to_local(self, obj: Any) -> Any:  # noqa: PLR6301
        local_tz = dt.datetime.now().astimezone().tzinfo

        if isinstance(obj, dt.datetime):
            # Treat naive datetimes as UTC (TeslaMate timestamps are stored without TZ)
            utc_dt = obj if obj.tzinfo is not None else obj.replace(tzinfo=dt.UTC)
            local_dt = utc_dt.astimezone(local_tz)
            return local_dt
        return obj
