import pytest
from app.db.store import Store
from app.domain.service import Service


class Clock:
    now = 1000.0
    def __call__(self):
        return self.now


@pytest.fixture
def setup(tmp_path):
    clock = Clock()
    return Service(Store(str(tmp_path / 'test.db'), True), clock), clock
