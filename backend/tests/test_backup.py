import subprocess
import sys
from pathlib import Path

from app.db.store import Store
from app.domain.service import Service
from helpers import act, deliver, event


def test_online_backup_restore_roundtrip(tmp_path):
    root = Path(__file__).resolve().parents[2]
    live = tmp_path / "live"
    service = Service(Store(str(live / "simulation.sqlite3"), True))
    original = service.event(event(category="BILL"))["request"]
    original = service.action(original["id"], "dispatch", act(1, staff_id=1))
    deliver(service, original)
    archive = tmp_path / "backup.sqlite3"
    command = [sys.executable, str(root / "tools/backup.py")]
    subprocess.run(
        [
            *command,
            "backup",
            "--mode",
            "simulation",
            "--data-dir",
            str(live),
            "--file",
            str(archive),
        ],
        check=True,
        capture_output=True,
    )
    destination = tmp_path / "restored"
    subprocess.run(
        [
            *command,
            "restore",
            "--mode",
            "simulation",
            "--data-dir",
            str(destination),
            "--file",
            str(archive),
            "--confirm-restore",
        ],
        check=True,
        capture_output=True,
    )
    restored = Service(Store(str(destination / "simulation.sqlite3"), True))
    assert restored.snapshot()["requests"] == service.snapshot()["requests"]
    for table in ("processed", "outbox", "events", "assignments", "correlations"):
        query = f"SELECT * FROM {table} ORDER BY rowid"
        assert restored.store.read(query) == service.store.read(query)
    # The event record, including its original central timestamps, is part of the backup.
    assert [e["type"] for e in restored.event_log(ascending=True)["items"]] == [
        "REGISTERED",
        "DISPATCHED",
        "DELIVERED",
    ]
