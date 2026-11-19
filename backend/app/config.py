"""Runtime configuration from the environment. Defaults are the logbook's proposed values.

Proposed/assumed values (Step 3 Table 3.4.1, Step 4): 5 s active poll, ≤1 s double-press
window, 5 min reminder, 10 s unresolved-state interval. They stay configurable because the
logbook keeps them open until the user trials and bench tests are done.
"""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    mode: str = "simulation"
    data_dir: str = "data"
    venue_id: int = 1
    serial_port: str = ""
    serial_baud: int = 115200
    poll_seconds: float = 5
    staff_poll_seconds: float = 2
    double_ms: int = 1000
    reminder_seconds: int = 300
    unresolved_seconds: int = 10
    retention_days: int = 90
    low_battery_mv: int = 0
    staff_token: str = ""
    staff_id: int = 1

    def __post_init__(self):
        if self.mode not in ("simulation", "hardware"):
            raise ValueError("PBL_MODE must be simulation or hardware")
        if not 0.1 <= self.poll_seconds <= 60 or not 100 <= self.double_ms <= 2000:
            raise ValueError("Invalid polling/double press config")
        if not 0.1 <= self.staff_poll_seconds <= 60:
            raise ValueError("Invalid PBL_STAFF_POLL_SECONDS")
        if not 1 <= self.venue_id <= 65535:
            raise ValueError("PBL_VENUE_ID must be 1..65535")
        if not 10 <= self.reminder_seconds <= 86400:
            raise ValueError("Invalid PBL_REMINDER_SECONDS")
        if not 2 <= self.unresolved_seconds <= 600:
            raise ValueError("Invalid PBL_UNRESOLVED_SECONDS")
        if self.retention_days < 30:
            raise ValueError("PBL_RETENTION_DAYS must be at least 30 (ER-F11)")
        if not 0 <= self.low_battery_mv <= 10000:
            raise ValueError("Invalid PBL_LOW_BATTERY_MV")

    @property
    def database(self):
        return str(Path(self.data_dir) / f"{self.mode}.sqlite3")

    @classmethod
    def environment(cls):
        return cls(
            mode=os.getenv("PBL_MODE", "simulation"),
            data_dir=os.getenv("PBL_DATA_DIR", "data"),
            venue_id=int(os.getenv("PBL_VENUE_ID", "1")),
            serial_port=os.getenv("PBL_SERIAL_PORT", ""),
            serial_baud=int(os.getenv("PBL_SERIAL_BAUD", "115200")),
            poll_seconds=float(os.getenv("PBL_POLL_SECONDS", "5")),
            staff_poll_seconds=float(os.getenv("PBL_STAFF_POLL_SECONDS", "2")),
            double_ms=int(os.getenv("PBL_DOUBLE_MS", "1000")),
            reminder_seconds=int(os.getenv("PBL_REMINDER_SECONDS", "300")),
            unresolved_seconds=int(os.getenv("PBL_UNRESOLVED_SECONDS", "10")),
            retention_days=int(os.getenv("PBL_RETENTION_DAYS", "90")),
            low_battery_mv=int(os.getenv("PBL_LOW_BATTERY_MV", "0")),
            staff_token=os.getenv("PBL_STAFF_TOKEN", ""),
            staff_id=int(os.getenv("PBL_STAFF_ID", "1")),
        )
