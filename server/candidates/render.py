"""Render the candidate pages at one pinned time.

    PYTHONPATH=. .venv/bin/python candidates/render.py 2026-09-04T11:42
"""
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from candidates.pool import candidate_pages
from epd_server import regenerate
from server import make_source
from sources.status import DeviceReports

logging.basicConfig(level=logging.INFO)
tz = ZoneInfo("Europe/Dublin")
at = datetime.strptime(sys.argv[1], "%Y-%m-%dT%H:%M").replace(tzinfo=tz).timestamp()
source = make_source(7, lambda: at, DeviceReports(), altitude_m=10)
regenerate(candidate_pages(tz, width=1280, height=720), source)
