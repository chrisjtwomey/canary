#!/usr/bin/env python3
"""Inkplate 5 env monitor server.

``epd_server.DisplayServer`` does the generic work: routes, the X-Next-*
headers, the regeneration loop, signals. This file is the project: its
config keys, its readings source, its pages, and one run() call.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime

from epd_server import DisplayServer, align_process_timezone
from epd_server.config import ConfigError, get_prop_by_keys, load_core_config, load_yaml
from epd_server.source import CompositeSource

from pages.air import AirPage
from pages.breathe import BreathePage
from pages.comfort import ComfortPage
from pages.day import DayPage
from pages.diagnostics import DiagnosticsPage
from pages.dust import DustPage
from pages.pool import PRESSURE, DeltaPage, TracePage
from sources.corrections import SeaLevelSource
from sources.mock import MockReadingsSource
from sources.status import DeviceReports, StatusSource

cwd = os.path.dirname(os.path.realpath(__file__))
log = logging.getLogger("server")

DEFAULT_SCHEDULE = {"07:00:00": "breathe.png"}


def make_pages(tz, **geometry) -> list:
    return [
        BreathePage("breathe", tz=tz, **geometry),
        ComfortPage("comfort", tz=tz, **geometry),
        DayPage("day", tz=tz, **geometry),
        DustPage("dust", tz=tz, **geometry),
        AirPage("air", tz=tz, **geometry),
        # the barometer pool: the record, and the change with its meaning
        TracePage("barometer-trace", PRESSURE, tz=tz, **geometry),
        DeltaPage("barometer-delta", PRESSURE, tz=tz, **geometry),
        DiagnosticsPage("diagnostics", tz=tz, **geometry),
    ]


def make_source(seed: int, clock, reports: DeviceReports, altitude_m: float = 0.0) -> CompositeSource:
    """The simulated room for the measurements, pressure reduced to sea
    level, and the board's own reports for the diagnostics."""
    room = SeaLevelSource(MockReadingsSource(seed=seed, now=clock), altitude_m)
    return CompositeSource(room, StatusSource(reports))


def parse_args():
    p = argparse.ArgumentParser(description="Inkplate 5 env monitor server")
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
        core = load_core_config(config, default_schedule=DEFAULT_SCHEDULE,
                                default_width=1280, default_height=720)
        kind = get_prop_by_keys(config, "source", "kind", default="mock")
        if kind != "mock":
            raise ConfigError(f"source.kind {kind!r} is not supported yet; use mock")
        seed = int(get_prop_by_keys(config, "source", "seed", default=7))
        altitude_m = float(get_prop_by_keys(config, "site", "altitude_m", default=0))
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

    reports = DeviceReports()
    source = make_source(seed, clock, reports, altitude_m)
    pages = make_pages(tz, **core.image.page_kwargs())

    try:
        server = DisplayServer(
            pages=pages,
            source=source,
            schedule=core.server.display_schedule,
            tz=tz,
            regen_lead_seconds=core.server.regen_lead_seconds,
            port=core.server.port,
            mqtt=core.mqtt,
            mqtt_client_id="env-monitor-server",
            ingest={"readings": reports.accept},
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
