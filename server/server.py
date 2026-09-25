#!/usr/bin/env python3
"""CANARY server.

``epd_server.DisplayServer`` does the generic work: routes, the Canary-Next-*
headers, the regeneration loop, signals. This file is the project: its
config keys, its readings source, its pages, and one run() call.
"""
from __future__ import annotations

import argparse
import dataclasses
import logging
import os
import sys
import threading
import time
from datetime import datetime
from typing import Callable

import yaml
from epd_server import DisplayServer, LogStore, ReadingsStore, align_process_timezone
from epd_server.config import (ConfigError, CoreConfig, get_prop_by_keys, load_core_config,
                               load_yaml)
from epd_server.firmware import is_clean_tag
from epd_server.source import CompositeSource, IngestSource

from about import About
from board_logs import LogsQuery
from config_page import config_blueprint
from dock_settings import DOCK, BoardSettings, DockSettings, load_dock_settings
from pages.air import AirPage
from pages.breathe import BreathePage
from pages.comfort import ComfortPage
from pages.day import DayPage
from pages.diagnostics import DiagnosticsPage, DiagnosticsTracePage, HealthTracePage
from pages.dust import DustPage
from pages.pool import CO2, IAQ, PM25, PRESSURE, TEMP, DeltaPage, TracePage
from schedule import DEFAULT_DOCK_SYNC, ClockSchedule
from sources.calibration import CalibrationStore
from sources.corrections import SeaLevelSource, to_sea_level
from sources.mock import MockReadingsSource
from sources.readings import ReadingsIngest, ReadingsQuery
from sources.status import DeviceReports, StatusSource
from transfer import Transfer
from version import server_version
from web import HistoryQuery, web_blueprint

cwd = os.path.dirname(os.path.realpath(__file__))
log = logging.getLogger("server")

# One page an hour when config.yaml has no display block.
DEFAULT_DISPLAY = {"pools": {"co2": ["breathe.png"]},
                   "schedule": {"type": "interval", "every": 3600}}

SOURCE_KINDS = ("mock", "store")
# The two boards, each with its images in a subdirectory of the firmware
# directory named after it.
FIRMWARE_PRODUCTS = ("canary-head", "canary-dock")
# The history windows the pages ask for, as history_24h and history_72h.
HISTORY_HOURS = (24, 72)
# The head reports on its own clock, kReportIntervalMs in src/main.cpp.
HEAD_REPORT_EVERY_S = 60


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


def make_between(seed: int, clock,
                 store: ReadingsStore | None = None) -> Callable[[int, int], list[dict]]:
    """The readings between two times, oldest first, as the boards posted
    them: the store's when there is one, and the simulated room's when not."""
    return store.between if store is not None else MockReadingsSource(seed=seed, now=clock).between


def make_history(between: Callable[[int, int], list[dict]],
                 altitude_m: float = 0.0) -> Callable[[int, int], list[dict]]:
    """``between`` as the pages see it, with pressure at sea level."""
    return lambda start, end: [to_sea_level(d, altitude_m) for d in between(start, end)]


def follow_own_version(firmware, version: str):
    """``firmware`` offering development builds exactly when this server runs
    one: a server past a tag is a development deployment, and its boards take
    what the builder beside it builds; a tagged server moves them between
    releases only."""
    return dataclasses.replace(firmware, offer_dev_builds=not is_clean_tag(version))


def make_silence(dock_sync: ClockSchedule) -> Callable[[str, float], float]:
    """How long each board may go without a report before two of its syncs
    are missed: the dock's since the second-latest slot, the head's two of
    its intervals."""
    def silence(device: str, now: float) -> float:
        if device != DOCK:
            return 2 * HEAD_REPORT_EVERY_S
        latest = dock_sync.slot_before(now)
        before = dock_sync.slot_before(latest - 1) if latest is not None else None
        return now - before if before is not None else float("inf")
    return silence


def make_next_sync(dock_sync: ClockSchedule) -> Callable[[str, float], int | None]:
    """The seconds until the dock's next sync slot; the head has none."""
    def next_sync(device: str, now: float) -> int | None:
        return dock_sync.seconds_until_next(now) if device == DOCK else None
    return next_sync


def make_dock_sync(config: dict, tz) -> ClockSchedule:
    """The dock's sync schedule from ``dock.sync``: every five minutes, and
    every half hour from 01:00 to 07:00, when config.yaml gives none.

    Raises:
        ConfigError: the schedule cannot work, or no range of it syncs, so
            the dock would take no readings at all.
    """
    value = get_prop_by_keys(config, "dock", "sync", default=DEFAULT_DOCK_SYNC)
    try:
        sync = ClockSchedule.from_config(value, tz, "dock.sync")
    except ValueError as exc:
        raise ConfigError(str(exc)) from None
    if sync.seconds_until_next(time.time()) is None:
        raise ConfigError("dock.sync has no range that syncs, so the dock would take no "
                          "readings: give one range an interval")
    return sync


@dataclasses.dataclass(frozen=True)
class Settings:
    """Everything the server takes from config.yaml."""
    core: CoreConfig
    kind: str
    seed: int
    store_path: str
    keep_days: float
    calibration_path: str
    calibration_days: float
    status_path: str
    status_days: float
    logs_path: str
    logs_days: float
    altitude_m: float
    dock_sync: ClockSchedule
    dock: DockSettings


def load_settings(config: dict) -> Settings:
    """The settings in ``config``, checked as the server checks them at start.

    Raises:
        ConfigError, KeyError, ValueError: the first problem, with a message
            for the person editing the file.
    """
    core = load_core_config(config, default_display=DEFAULT_DISPLAY,
                            default_firmware_product="canary-head",
                            default_mqtt_prefix="mqtt/canary",
                            base_dir=cwd,
                            default_width=1280, default_height=720)
    kind = get_prop_by_keys(config, "source", "kind", default="mock")
    if kind not in SOURCE_KINDS:
        raise ConfigError(f"source.kind {kind!r} is not one of {', '.join(SOURCE_KINDS)}")
    served = {p.png_filename for p in make_pages(core.server.timezone, **core.image.page_kwargs())}
    unknown = sorted(core.server.schedule.pages() - served)
    if unknown:
        raise ConfigError(f"display.pools name {', '.join(unknown)}, which no page produces")
    if not core.firmware.products:
        core = dataclasses.replace(core, firmware=dataclasses.replace(
            core.firmware, products=FIRMWARE_PRODUCTS))
    return Settings(
        core=core,
        kind=kind,
        seed=int(get_prop_by_keys(config, "source", "seed", default=7)),
        store_path=str(get_prop_by_keys(config, "source", "path", default="sensor-readings.db")),
        keep_days=float(get_prop_by_keys(config, "source", "keep_days", default=0)),
        calibration_path=str(get_prop_by_keys(config, "calibration", "path",
                                              default="calibration.db")),
        calibration_days=float(get_prop_by_keys(config, "calibration", "keep_days", default=3)),
        status_path=str(get_prop_by_keys(config, "status", "path", default="status.db")),
        status_days=float(get_prop_by_keys(config, "status", "keep_days", default=7)),
        logs_path=str(get_prop_by_keys(config, "logs", "path", default="board-logs.db")),
        logs_days=float(get_prop_by_keys(config, "logs", "keep_days", default=7)),
        altitude_m=float(get_prop_by_keys(config, "site", "altitude_m", default=0)),
        dock_sync=make_dock_sync(config, core.server.timezone),
        dock=load_dock_settings(config),
    )


def check_config(text: str) -> None:
    """Refuse ``text``, with the problem, unless the server would start on it.

    Raises:
        ValueError: the text is not YAML, or load_settings refuses it. Any
            error load_settings meets is a refusal, since the same error at
            start would stop the server.
    """
    try:
        config = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"It is not YAML: {exc}") from None
    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise ValueError("The top level must be a mapping.")
    try:
        load_settings(config)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(exc.args[0] if exc.args else repr(exc)) from None


def restart_soon(delay_s: float = 1.0) -> None:
    """Start this process again on the config as it now is, once the response
    to the request that asked for it has gone out."""
    def again():
        log.info("restarting on the new config")
        sys.stdout.flush()
        sys.stderr.flush()
        os.execv(sys.executable, [sys.executable, os.path.abspath(sys.argv[0])] + sys.argv[1:])
    threading.Timer(delay_s, again).start()


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
        settings = load_settings(config)
    except (ConfigError, KeyError, ValueError) as exc:
        logging.basicConfig()
        log.error(exc.args[0] if exc.args else str(exc))
        sys.exit(1)
    version = server_version()
    core = dataclasses.replace(settings.core,
                               firmware=follow_own_version(settings.core.firmware, version))

    logging.basicConfig(level=logging.DEBUG if core.server.debug else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log.info("canary %s: development builds are %soffered", version,
             "" if core.firmware.offer_dev_builds else "not ")
    align_process_timezone(core.server.timezone)
    tz = core.server.timezone

    clock = time.time
    if args.at:
        pinned = datetime.strptime(args.at, "%Y-%m-%dT%H:%M").replace(tzinfo=tz).timestamp()
        clock = lambda: pinned  # noqa: E731
        log.info("clock pinned to %s", args.at)

    status_store = ReadingsStore(os.path.join(cwd, settings.status_path))
    reports = DeviceReports(store=status_store, keep_days=settings.status_days,
                            silence=make_silence(settings.dock_sync),
                            next_sync=make_next_sync(settings.dock_sync))
    log.info("board reports in %s, %d held", status_store.path, status_store.count())
    store = None
    if settings.kind == "store":
        store = ReadingsStore(os.path.join(cwd, settings.store_path))
        log.info("readings from %s, %d held", store.path, store.count())
    source = make_source(settings.seed, clock, reports, settings.altitude_m, store)
    calibration = CalibrationStore(os.path.join(cwd, settings.calibration_path),
                                   keep_days=settings.calibration_days)
    ingest = ReadingsIngest(reports, store, settings.keep_days)
    dock_sync = settings.dock_sync
    about = About(version, core.firmware, dock_sync=dock_sync)
    pages = make_pages(tz, **core.image.page_kwargs())
    between = make_between(settings.seed, clock, store)
    history = HistoryQuery(make_history(between, settings.altitude_m), tz, now=clock)
    readings = ReadingsQuery(between, now=clock)
    status = StatusSource(reports)
    board_logs = LogStore(os.path.join(cwd, settings.logs_path), keep_days=settings.logs_days)
    logs = LogsQuery(board_logs, tz)
    board_settings = BoardSettings(settings.dock, dock_sync, calibration, reports.device, now=clock)

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
            client_logs=board_logs,
            ingest={"sensor-readings": ingest.accept, "calibration": calibration.accept},
            queries={"calibration": calibration.answer, "about": about.answer,
                     "board-settings": board_settings.answer,
                     "history": history.answer, "sensor-readings": readings.answer,
                     "status": lambda args: status.status(), "logs": logs.answer},
            firmware=core.firmware,
            header_prefix="Canary",
            server_version=about.version,
            version_gate=True,
            sensor_poll=dock_sync.seconds_until_next,
            on_refused=reports.refused,
        )
    except ValueError as exc:
        log.error(str(exc))
        sys.exit(1)
    server.app.register_blueprint(web_blueprint(pages, source, logging_on=core.mqtt.enabled))
    stores = {
        "sensor-readings": Transfer("sensor-readings", os.path.join(cwd, settings.store_path)),
        "board-reports": Transfer("board-reports", status_store.path),
        "calibration": Transfer("calibration", calibration.path, "calibration"),
        "board-logs": Transfer("board-logs", board_logs.path, "logs"),
    }
    server.app.register_blueprint(config_blueprint(pages, os.path.join(cwd, "config.yaml"),
                                                   check_config, restart_soon, stores,
                                                   dock=board_settings, boards=reports.device))

    if args.once or args.only:
        server.regenerate(only=args.only)
        return
    server.run()


if __name__ == "__main__":
    main()
