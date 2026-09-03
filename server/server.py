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

from pages.breathe import BreathePage
from pages.comfort import ComfortPage
from pages.day import DayPage
from sources.mock import MockReadingsSource

cwd = os.path.dirname(os.path.realpath(__file__))
log = logging.getLogger("server")

DEFAULT_SCHEDULE = {"07:00:00": "breathe.png"}


def make_pages(tz, **geometry) -> list:
    return [
        BreathePage("breathe", tz=tz, **geometry),
        ComfortPage("comfort", tz=tz, **geometry),
        DayPage("day", tz=tz, **geometry),
    ]


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
    except (ConfigError, KeyError) as exc:
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

    source = MockReadingsSource(seed=seed, now=clock)
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
