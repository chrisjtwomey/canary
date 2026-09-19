#!/usr/bin/env python3
"""CANARY server.

``epd_server.DisplayServer`` does the generic work: routes, the X-Next-*
headers, the regeneration loop, signals. This file is the project: its
config keys, its readings source, its pages, and one run() call.
"""
from __future__ import annotations

import argparse
import dataclasses
import logging
import os
import sys
import time
from datetime import datetime

from epd_server import DisplayServer, ReadingsStore, align_process_timezone
from epd_server.config import ConfigError, get_prop_by_keys, load_core_config, load_yaml
from epd_server.source import CompositeSource, IngestSource

from about import About
from pages.air import AirPage
from pages.breathe import BreathePage
from pages.comfort import ComfortPage
from pages.day import DayPage
from pages.diagnostics import DiagnosticsPage, DiagnosticsTracePage, HealthTracePage
from pages.dust import DustPage
from pages.pool import CO2, IAQ, PM25, PRESSURE, TEMP, DeltaPage, TracePage
from schedule import PostSchedule, parse_hhmm
from sources.calibration import CalibrationStore
from sources.corrections import SeaLevelSource
from sources.mock import MockReadingsSource
from sources.readings import ReadingsIngest
from sources.status import DeviceReports, StatusSource
from version import server_version

cwd = os.path.dirname(os.path.realpath(__file__))
log = logging.getLogger("server")

# One page an hour when config.yaml has no display block.
DEFAULT_DISPLAY = {"pools": {"co2": ["breathe.png"]},
                   "schedule": {"type": "interval", "every": 3600}}

SOURCE_KINDS = ("mock", "store")
# The two boards, each with its images in a subdirectory of the firmware
# directory named after it.
FIRMWARE_PRODUCTS = ("canary-head", "canary-dock")
# The dock posts every half hour overnight unless config.yaml says otherwise.
DEFAULT_QUIET = {"from": "01:00", "to": "07:00", "every": 1800}
# The history windows the pages ask for, as history_24h and history_72h.
HISTORY_HOURS = (24, 72)


def make_pages(tz, **geometry) -> list:
    """Every page the server can serve. Which ones show, and in what order,
    is the display block's business; see config.example.yaml."""
    pages = [
        BreathePage("breathe", tz=tz, **geometry),
        ComfortPage("comfort", tz=tz, **geometry),
        DustPage("dust", tz=tz, **geometry),
        AirPage("air", tz=tz, **geometry),
        DayPage("day", tz=tz, **geometry),
        DiagnosticsPage("diagnostics", tz=tz, **geometry),
        DiagnosticsTracePage("diagnostics-trace", tz=tz, **geometry),
        HealthTracePage("health-trace", tz=tz, **geometry),
    ]
    for stem, metric in (("co2", CO2), ("comfort", TEMP), ("dust", PM25), ("air", IAQ),
                         ("barometer", PRESSURE)):
        pages.append(TracePage(f"{stem}-trace", metric, tz=tz, **geometry))
        pages.append(DeltaPage(f"{stem}-delta", metric, tz=tz, **geometry))
    return pages


def make_source(seed: int, clock, reports: DeviceReports, altitude_m: float = 0.0,
                store: ReadingsStore | None = None) -> CompositeSource:
    """The measurements, pressure reduced to sea level, and the board's own
    reports for the diagnostics. The measurements are what the board posted
    when there is a store, and the simulated room when there is not."""
    if store is not None:
        readings = IngestSource(store, hours=HISTORY_HOURS, now=clock)
    else:
        readings = MockReadingsSource(seed=seed, now=clock)
    return CompositeSource(SeaLevelSource(readings, altitude_m), StatusSource(reports))


def make_posts(config: dict, tz) -> PostSchedule:
    """The dock's post schedule from the ``posts`` block: every five minutes,
    and every half hour from 01:00 to 07:00, when the block says nothing."""
    quiet = get_prop_by_keys(config, "posts", "quiet", default=DEFAULT_QUIET) or {}
    every = int(get_prop_by_keys(config, "posts", "every", default=300))
    if not quiet:
        return PostSchedule(every, tz)
    return PostSchedule(every, tz, parse_hhmm(quiet.get("from", "")),
                        parse_hhmm(quiet.get("to", "")), int(quiet.get("every", every)))


def parse_args():
    p = argparse.ArgumentParser(description="CANARY server")
    p.add_argument("--once", action="store_true",
                   help="Render the images and exit. No HTTP server, no scheduler.")
    p.add_argument("--only", metavar="PAGE",
                   help="Render one page and exit, e.g. breathe.png. Implies --once.")
    p.add_argument("--at", metavar="YYYY-MM-DDTHH:MM",
                   help="Pin the clock the source and the pages see, in server.timezone.")
    return p.parse_args()


def main():
    args = parse_args()
    config = load_yaml(os.path.join(cwd, "config.yaml"))

    try:
        core = load_core_config(config, default_display=DEFAULT_DISPLAY,
                                default_firmware_product="canary-head",
                                base_dir=cwd,
                                default_width=1280, default_height=720)
        kind = get_prop_by_keys(config, "source", "kind", default="mock")
        if kind not in SOURCE_KINDS:
            raise ConfigError(f"source.kind {kind!r} is not one of {', '.join(SOURCE_KINDS)}")
        seed = int(get_prop_by_keys(config, "source", "seed", default=7))
        store_path = str(get_prop_by_keys(config, "source", "path", default="readings.db"))
        keep_days = float(get_prop_by_keys(config, "source", "keep_days", default=0))
        calibration_path = str(get_prop_by_keys(config, "calibration", "path",
                                                default="calibration.db"))
        calibration_days = float(get_prop_by_keys(config, "calibration", "keep_days", default=3))
        status_path = str(get_prop_by_keys(config, "status", "path", default="status.db"))
        status_days = float(get_prop_by_keys(config, "status", "keep_days", default=7))
        altitude_m = float(get_prop_by_keys(config, "site", "altitude_m", default=0))
        posts = make_posts(config, core.server.timezone)
        if not core.firmware.products:
            core = dataclasses.replace(core, firmware=dataclasses.replace(
                core.firmware, products=FIRMWARE_PRODUCTS))
    except (ConfigError, KeyError, ValueError) as exc:
        logging.basicConfig()
        log.error(exc.args[0] if exc.args else str(exc))
        sys.exit(1)

    logging.basicConfig(level=logging.DEBUG if core.server.debug else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    align_process_timezone(core.server.timezone)
    tz = core.server.timezone

    clock = time.time
    if args.at:
        pinned = datetime.strptime(args.at, "%Y-%m-%dT%H:%M").replace(tzinfo=tz).timestamp()
        clock = lambda: pinned  # noqa: E731
        log.info("clock pinned to %s", args.at)

    status_store = ReadingsStore(os.path.join(cwd, status_path))
    reports = DeviceReports(store=status_store, keep_days=status_days)
    log.info("board reports in %s, %d held", status_store.path, status_store.count())
    store = None
    if kind == "store":
        store = ReadingsStore(os.path.join(cwd, store_path))
        log.info("readings from %s, %d held", store.path, store.count())
    source = make_source(seed, clock, reports, altitude_m, store)
    calibration = CalibrationStore(os.path.join(cwd, calibration_path), keep_days=calibration_days)
    ingest = ReadingsIngest(reports, store, keep_days)
    about = About(server_version(), core.firmware, posts=posts)
    pages = make_pages(tz, **core.image.page_kwargs())

    try:
        server = DisplayServer(
            pages=pages,
            source=source,
            schedule=core.server.schedule,
            tz=tz,
            regen_lead_seconds=core.server.regen_lead_seconds,
            port=core.server.port,
            mqtt=core.mqtt,
            mqtt_client_id="canary-server",
            ingest={"readings": ingest.accept, "calibration": calibration.accept},
            queries={"calibration": calibration.answer, "about": about.answer},
            firmware=core.firmware,
            header_prefix="Canary",
            server_version=about.version,
            version_gate=True,
            sensor_poll=posts.seconds_until_next,
            on_refused=reports.refused,
        )
    except ValueError as exc:
        log.error(str(exc))
        sys.exit(1)

    if args.once or args.only:
        server.regenerate(only=args.only)
        return
    server.run()


if __name__ == "__main__":
    main()
