from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from sources.mock import MockReadingsSource

TZ = ZoneInfo("Europe/Dublin")
AT = int(datetime(2026, 9, 3, 21, 45, tzinfo=TZ).timestamp())


@pytest.fixture
def tz():
    return TZ


@pytest.fixture
def source():
    return MockReadingsSource(seed=7, now=lambda: AT)


@pytest.fixture
def data(source):
    ds = source.datasets()
    return {"latest": ds["latest"](), "history_24h": ds["history_24h"]()}
