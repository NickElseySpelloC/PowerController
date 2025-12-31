from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime
    from decimal import Decimal


@dataclass(frozen=True)
class ChargingSession:
    id: int
    car_id: int
    start_date: datetime
    end_date: datetime | None
    duration_min: int | None
    start_battery_level: int | None
    end_battery_level: int | None
    charge_energy_added_kwh: Decimal | None  # TO DO: convert all Decimal instances to float
    charge_energy_used_kwh: Decimal | None
    cost: Decimal | None
    geofence_name: str | None = None
    short_address: str | None = None


@dataclass(frozen=True)
class EnergyBucket:
    charging_process_id: int
    bucket_start: datetime
    bucket_end: datetime
    kwh_added: Decimal
    avg_kw: Decimal  # kWh in 5 minutes * 12


@dataclass(frozen=True)
class TeslaImportResult:
    start_date: datetime
    sessions: list[ChargingSession]
    buckets: list[EnergyBucket]
