import os
import tempfile

import pytest

# app.main builds its default application at import time. Point it at a throwaway directory
# so running the tests never opens or migrates the operator's real data/ profile.
os.environ["PBL_DATA_DIR"] = tempfile.mkdtemp(prefix="pbl4-tests-")
os.environ["PBL_MODE"] = "simulation"

from app.db.store import Store  # noqa: E402
from app.domain.service import Service  # noqa: E402


class Clock:
    now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def setup(tmp_path):
    clock = Clock()
    return Service(Store(str(tmp_path / "test.db"), True), clock), clock
