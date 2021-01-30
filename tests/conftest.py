import datetime

import freezegun
import pytest
from responses import RequestsMock

from tests.util.mock_db import MockDB


@pytest.fixture()
def mock_db():
    return MockDB()


@pytest.fixture()
def mock_requests():
    with RequestsMock() as reqs:
        yield reqs


@pytest.fixture()
def freeze_time():
    # Make sure some randomness in the time doesn't break a test
    dt = datetime.datetime(2019, 8, 22, 18, 14, 36)
    diff = datetime.datetime.now() - datetime.datetime.utcnow()
    ts = round(diff.total_seconds() / (15 * 60)) * (15 * 60)
    tz = datetime.timedelta(seconds=ts)

    with freezegun.freeze_time(dt, tz) as ft:
        yield ft
