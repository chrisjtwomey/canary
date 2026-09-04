"""Serve the candidate pages to the board, one a minute, to see them on the
panel. Every regular page is served too, so whatever URL the board holds
still resolves.

    PYTHONPATH=. .venv/bin/python candidates/serve.py [seconds per page, default 60]

The cadence is the server's alone: every fetch tells the board when to
come back and for which page.
"""
import logging
import os
import sys
import time

from epd_server import DisplayServer, align_process_timezone
from epd_server.config import expand_interval_schedule, load_core_config, load_yaml

from candidates.pool import candidate_pages
from server import make_pages, make_source
from sources.status import DeviceReports

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
here = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
core = load_core_config(load_yaml(os.path.join(here, "config.yaml")),
                        default_schedule={"00:00:00": "breathe.png"},
                        default_width=1280, default_height=720)
align_process_timezone(core.server.timezone)
tz = core.server.timezone
geometry = core.image.page_kwargs()

every = int(sys.argv[1]) if len(sys.argv) > 1 else 60
candidates = candidate_pages(tz, **geometry)
schedule = sorted(expand_interval_schedule(
    {"every": every, "pages": [p.png_filename for p in candidates]}).items())

reports = DeviceReports()
DisplayServer(
    pages=make_pages(tz, **geometry) + candidates,
    source=make_source(7, time.time, reports, altitude_m=10),
    schedule=schedule,
    tz=tz,
    regen_lead_seconds=min(20, every // 2),
    port=core.server.port,
    ingest={"readings": reports.accept},
).run()
