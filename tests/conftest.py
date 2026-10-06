import os

os.environ["VAY_STORE"] = "memory"
os.environ["VAY_SYNC_JOBS"] = "1"

import pytest

from server.store import reset_store_for_tests


@pytest.fixture(autouse=True)
def _memory_store():
    reset_store_for_tests()
    yield
