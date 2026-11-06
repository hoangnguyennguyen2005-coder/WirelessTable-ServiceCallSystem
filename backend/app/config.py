import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    mode: str = "simulation"
    data_dir: str = "data"
    serial_port: str = ""
    serial_baud: int = 115200
    poll_seconds: float = 5
    double_ms: int = 600
    staff_token: str = ""
    staff_id: int = 1

    def __post_init__(self):
        if self.mode not in ("simulation", "hardware"):
            raise ValueError("PBL_MODE must be simulation or hardware")
        if not 0.1 <= self.poll_seconds <= 60 or not 100 <= self.double_ms <= 2000:
            raise ValueError("Invalid polling/double press config")

    @property
    def database(self):
        return str(Path(self.data_dir) / f"{self.mode}.sqlite3")

    @classmethod
    def environment(cls):
        return cls(
            mode=os.getenv("PBL_MODE", "simulation"),
            data_dir=os.getenv("PBL_DATA_DIR", "data"),
            serial_port=os.getenv("PBL_SERIAL_PORT", ""),
            serial_baud=int(os.getenv("PBL_SERIAL_BAUD", "115200")),
            poll_seconds=float(os.getenv("PBL_POLL_SECONDS", "5")),
            double_ms=int(os.getenv("PBL_DOUBLE_MS", "600")),
            staff_token=os.getenv("PBL_STAFF_TOKEN", ""),
            staff_id=int(os.getenv("PBL_STAFF_ID", "1")),
        )
