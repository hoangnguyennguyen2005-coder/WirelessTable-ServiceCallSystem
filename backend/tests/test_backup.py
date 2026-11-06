import subprocess
import sys
from pathlib import Path
from app.db.store import Store
from app.domain.service import Service
from test_domain import event


def test_online_backup_restore_roundtrip(tmp_path):
    root = Path(__file__).resolve().parents[2]
    live = tmp_path / "live"
    service = Service(Store(str(live / "simulation.sqlite3"), True))
    original = service.event(event())["request"]
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
    assert restored.snapshot()["requests"][0] == original
    assert restored.store.read("SELECT * FROM processed") == service.store.read(
        "SELECT * FROM processed"
    )
    assert restored.store.read("SELECT * FROM outbox") == service.store.read(
        "SELECT * FROM outbox"
    )
