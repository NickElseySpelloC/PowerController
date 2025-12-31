from __future__ import annotations

import os
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from sc_utility import SCConfigManager

load_dotenv()


class DbConfig:
    def __init__(self, config: SCConfigManager):
        self.enabled: bool = bool(config.get("TeslaMate", "Enable", default=False))
        self.host: str = str(os.getenv("TESLAMATE_DB_HOST", config.get("TeslaMate", "Host", default="127.0.0.1")))
        self.port: int = int(os.getenv("TESLAMATE_DB_PORT", config.get("TeslaMate", "Port", default=5432)))  # pyright: ignore[reportArgumentType]
        self.dbname: str = str(os.getenv("TESLAMATE_DB_NAME", config.get("TeslaMate", "DatabaseName", default="teslamate")))
        self.user: str = str(os.getenv("TESLAMATE_DB_USER", config.get("TeslaMate", "DBUsername", default="teslamate")))
        self.password: str = str(os.getenv("TESLAMATE_DB_PASSWORD", config.get("TeslaMate", "DBPassword", default="")))
        self.sslmode: str = "prefer"
        self.geofence_name: str | None = config.get("TeslaMate", "GeofenceName", default=None)  # pyright: ignore[reportAttributeAccessIssue]

    def dsn(self) -> str:
        # psycopg3 DSN string
        return (
            f"host={self.host} port={self.port} dbname={self.dbname} "
            f"user={self.user} password={self.password} sslmode={self.sslmode}"
        )
