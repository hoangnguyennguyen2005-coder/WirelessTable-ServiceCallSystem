"""Kiểm tra bổ sung UT-11 bước 1 cho phía HOÀN TẤT (không sửa code dự án).

Chạy tại thư mục gốc PBL4:
    .venv\\Scripts\\python.exe -m pytest -v -s evidence\\UT-11\\ut11_completion_fault.py
Commit đóng yêu cầu bị lỗi -> không có DONE_RECEIPT, yêu cầu vẫn mở.
Bàn gửi lại DONE (cùng danh tính) -> đóng đúng 1 lần.
"""
import os
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))
os.environ.setdefault("PBL_DATA_DIR", tempfile.mkdtemp(prefix="pbl4-extra-"))

import pytest  # noqa: E402
from app.db.store import Store  # noqa: E402
from app.domain.service import Service  # noqa: E402
from helpers import event, kinds  # noqa: E402


class BrokenCommit(Store):
    @contextmanager
    def transaction(self):
        with super().transaction() as db:
            yield db
            raise sqlite3.OperationalError("disk I/O error")


def test_failed_completion_commit_gives_no_done_receipt(tmp_path):
    path = str(tmp_path / "t.db")
    Service(Store(path, True)).event(event(category="BILL"))
    done = event("DONE")
    with pytest.raises(sqlite3.OperationalError):
        Service(BrokenCommit(path, True)).exchange(done)
    healthy = Service(Store(path, True))
    active = healthy.snapshot()["requests"]
    print("\nSau commit loi: so yeu cau mo =", len(active), "| trang thai =", active[0]["state"])
    assert len(active) == 1 and active[0]["state"] == "REGISTERED"
    frames = healthy.exchange(done)
    print("Gui lai DONE ->", [f["message_type"] for f in frames], frames[0]["payload"])
    assert frames[0]["message_type"] == "DONE_RECEIPT" and frames[0]["payload"]["led"] == "OFF"
    assert healthy.snapshot()["requests"] == []
    assert kinds(healthy).count("COMPLETED") == 1
    print("Nhat ky:", kinds(healthy))
