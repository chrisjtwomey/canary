"""Render the pressure candidates beside the current page.

    PYTHONPATH=. .venv/bin/python candidates/render.py 2026-09-04T11:42
"""
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from candidates.pressure import (BarographPage, ColumnPage, ComfortPressurePage, DayPressurePage,
                                 TendencyPage)
from sources.mock import MockReadingsSource

logging.basicConfig(level=logging.INFO)
tz = ZoneInfo("Europe/Dublin")
at = datetime.strptime(sys.argv[1], "%Y-%m-%dT%H:%M").replace(tzinfo=tz).timestamp()
src = MockReadingsSource(seed=7, now=lambda: at)
latest, h24, h72 = src.latest(), src.history(24), src.history(72)
geometry = dict(tz=tz, width=1280, height=720)

for page, data in (
    (BarographPage("barometer-barograph", **geometry), dict(latest=latest, history_72h=h72)),
    (TendencyPage("barometer-tendency", **geometry), dict(latest=latest, history_24h=h24)),
    (ColumnPage("barometer-column", **geometry), dict(latest=latest, history_24h=h24)),
    (DayPressurePage("day-pressure", **geometry), dict(latest=latest, history_24h=h24)),
    (ComfortPressurePage("comfort-pressure", **geometry), dict(latest=latest, history_24h=h24)),
):
    page.template(**data)
    page.save()
