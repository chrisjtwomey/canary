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
import math
import os
import sys
import threading
import time
from datetime import datetime, time as clock_time
from typing import Callable

import yaml
from epd_server import DisplayServer, LogStore, ReadingsStore, align_process_timezone
from epd_server.config import (ConfigError, CoreConfig, get_prop_by_keys, load_core_config,
                               load_yaml)
from epd_server.firmware import is_clean_tag
from epd_server.install import InstallBoard
from epd_server.scheduling import TimeRangesSchedule
from epd_server.source import CompositeSource, IngestSource
from epd_server.timeranges import TimeRanges, Week, check_interval

from about import About, config_version
from after_reading import AfterReadingSchedule
from board_logs import LogsQuery
from config_page import config_blueprint
from display_settings import DISPLAY, DisplaySync, display_version
from dock_settings import DOCK, BoardSettings, DockSettings, load_dock_settings
from metrics import COMFORT, Comfort, temp_along_feel
from off_hours import OffHoursSchedule, splash_when_off
from pages.air import AirPage
from pages.breathe import BreathePage
from pages.comfort import ComfortPage
from pages.day import DayPage
from pages.diagnostics import DiagnosticsPage, DiagnosticsTracePage, HealthTracePage
from pages.dust import DustPage
from pages.pool import CO2, IAQ, PM25, PRESSURE, DeltaPage, TracePage, comfort_metrics
from pages.splash import SplashPage, logo_svg
from schedule import DEFAULT_DISPLAY_SYNC_S, DEFAULT_DOCK_WEEK, DEFAULT_PAGE_WEEK
from sources.calibration import CalibrationStore
from sources.corrections import CorrectedSource, correct
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
                   "schedule": {"type": "timeranges", "week": DEFAULT_PAGE_WEEK}}

SOURCE_KINDS = ("mock", "store")
# The two boards, each with its images in a subdirectory of the firmware
# directory named after it.
FIRMWARE_PRODUCTS = ("canary-display", "canary-dock")
# The boards the install page offers, each with the USB vendor of its port:
# the display's CH340C, and the dock's ESP32-S3 itself.
INSTALL_BOARDS = (
    InstallBoard("canary-display", "Display", "ESP32", (0x1A86,)),
    InstallBoard("canary-dock", "Dock", "ESP32-S3", (0x303A,)),
)
# The HTTPS port's self-signed certificate, in the data volume, so that a
# browser that has accepted it keeps it across a redeploy.
CERTIFICATE_DIR = os.path.join(cwd, "data", "certificate")
# The history windows the pages ask for, as history_24h and history_72h.
HISTORY_HOURS = (24, 72)


def make_pages(tz, comfort: Comfort = COMFORT, **geometry) -> list:
    """Every page the server can serve. Which ones show, and in what order,
    is the display block's business; see config.example.yaml."""
    temp, _ = comfort_metrics(comfort)
    pages = [
        BreathePage("breathe", tz=tz, **geometry),
        ComfortPage("comfort", comfort=comfort, tz=tz, **geometry),
        DustPage("dust", tz=tz, **geometry),
        AirPage("air", tz=tz, **geometry),
        DayPage("day", tz=tz, **geometry),
        DiagnosticsPage("diagnostics", tz=tz, **geometry),
        DiagnosticsTracePage("diagnostics-trace", tz=tz, **geometry),
        HealthTracePage("health-trace", tz=tz, **geometry),
    ]
    for stem, metric in (("co2", CO2), ("comfort", temp), ("dust", PM25), ("air", IAQ),
                         ("barometer", PRESSURE)):
        pages.append(TracePage(f"{stem}-trace", metric, tz=tz, **geometry))
        pages.append(DeltaPage(f"{stem}-delta", metric, tz=tz, **geometry))
    return pages


def make_source(seed: int, clock, reports: DeviceReports, altitude_m: float = 0.0,
                store: ReadingsStore | None = None) -> CompositeSource:
    """The measurements, corrected (sources.corrections), and the board's own
    reports for the diagnostics. The measurements are what the board posted
    when there is a store, and the simulated room when there is not."""
    if store is not None:
        readings = IngestSource(store, hours=HISTORY_HOURS, now=clock)
    else:
        readings = MockReadingsSource(seed=seed, now=clock)
    return CompositeSource(CorrectedSource(readings, altitude_m), StatusSource(reports))


def make_between(seed: int, clock,
                 store: ReadingsStore | None = None) -> Callable[[int, int], list[dict]]:
    """The readings between two times, oldest first, as the boards posted
    them: the store's when there is one, and the simulated room's when not."""
    return store.between if store is not None else MockReadingsSource(seed=seed, now=clock).between


def make_history(between: Callable[[int, int], list[dict]],
                 altitude_m: float = 0.0) -> Callable[[int, int], list[dict]]:
    """``between`` as the pages see it, corrected (sources.corrections)."""
    return lambda start, end: [correct(d, altitude_m) for d in between(start, end)]


def follow_own_version(firmware, version: str):
    """``firmware`` offering development builds exactly when this server runs
    one: a server past a tag is a development deployment, and its boards take
    what the builder beside it builds; a tagged server moves them between
    releases only."""
    return dataclasses.replace(firmware, offer_dev_builds=not is_clean_tag(version))


def make_silence(syncs: dict[str, Week]) -> Callable[[str, float], float]:
    """How long each board may go without a report before two of its syncs
    are missed: since the second-latest slot of its own schedule. A board
    with no schedule, or no slot in it, is never judged."""
    def silence(device: str, now: float) -> float:
        sync = syncs.get(device)
        latest = sync.slot_before(now) if sync else None
        before = sync.slot_before(latest - 1) if latest is not None else None
        return now - before if before is not None else float("inf")
    return silence


PageWake = Callable[[float], tuple[float, float]]


def make_next_sync(syncs: dict[str, Week],
                   page_wake: PageWake | None = None) -> Callable[[str, float], int | None]:
    """The seconds until a board's next sync slot; None for a board with no
    schedule, or no slot in it. A display sync that falls between a page's
    slot and its wake (``page_wake``: AfterReadingSchedule.page_wake) moves to
    that wake, which posts the display's state anyway, so the display wakes
    once."""
    def next_sync(device: str, now: float) -> int | None:
        sync = syncs.get(device)
        seconds = sync.seconds_until_next(now) if sync else None
        if seconds is None or device != DISPLAY or page_wake is None:
            return seconds
        wake, after_slot = page_wake(now)
        if 0 <= wake - (now + seconds) <= after_slot:
            return max(1, math.ceil(wake - now))
        return seconds
    return next_sync


# A post this close before a board's slot is that slot's. The dock's clock
# runs fast in light sleep, about 0.6 s in 30 minutes, so its post can arrive
# just before the slot; an answer of "1 s" would make it read again at once.
SLOT_EARLY_S = 5


def make_sensor_poll(syncs: dict[str, Week],
                     page_wake: PageWake | None = None) -> Callable[[float, str | None], int | None]:
    """The Canary-Next-Sensor-Poll-Seconds each board gets: its own next sync,
    or the one after it when the post is up to SLOT_EARLY_S before a slot."""
    next_sync = make_next_sync(syncs, page_wake)

    def poll(now: float, name: str | None) -> int | None:
        if not name:
            return None
        seconds = next_sync(name, now)
        if seconds is None or seconds > SLOT_EARLY_S:
            return seconds
        after = next_sync(name, now + seconds)
        return None if after is None else seconds + after
    return poll


def make_display_sync(config: dict, tz) -> Week:
    """The display's sync schedule from ``display.sync.every``, one range all
    day every day: every half hour when config.yaml gives none. 0 is none,
    since the display also syncs at each page it fetches.

    Raises:
        ConfigError: the block is not ``{every: seconds}``, or the interval
            is not 0 or a whole number of minutes up to a day.
    """
    block = get_prop_by_keys(config, "display", "sync", default={})
    if not isinstance(block, dict) or set(block) - {"every"}:
        raise ConfigError(f"display.sync must be {{every: seconds}}, 0 for none, not {block!r}")
    try:
        every = check_interval(block.get("every", DEFAULT_DISPLAY_SYNC_S), "display.sync.every")
    except ValueError as exc:
        raise ConfigError(str(exc)) from None
    return Week.every_day(TimeRanges([(clock_time(0), every)], tz, "display.sync"))


def make_dock_sync(config: dict, tz) -> Week:
    """The dock's sync schedule from ``dock.sync.week``: every five minutes,
    and every half hour from 01:00 to 07:00, every day, when config.yaml
    gives none.

    Raises:
        ConfigError: the block is not ``{week: [...]}``, the week cannot
            work, or no range of it syncs, so the dock would take no
            readings at all.
    """
    block = get_prop_by_keys(config, "dock", "sync", default={})
    if not isinstance(block, dict) or set(block) - {"week"}:
        raise ConfigError("dock.sync must be {week: [...]}: groups of days, each "
                          "{days: [mon, ...], ranges: [{from, every}, ...]}")
    try:
        sync = Week.from_config(block.get("week", DEFAULT_DOCK_WEEK), tz, "dock.sync.week")
    except ValueError as exc:
        raise ConfigError(str(exc)) from None
    if not sync.slots_a_week():
        raise ConfigError("dock.sync.week has no range that syncs, so the dock would take no "
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
    comfort: Comfort
    dock_sync: Week
    display_sync: Week
    dock: DockSettings

    @property
    def syncs(self) -> dict[str, Week]:
        """Each board's sync schedule, by the name it states."""
        return {DOCK: self.dock_sync, DISPLAY: self.display_sync}


def load_comfort(config: dict) -> Comfort:
    """The comfort block's edges, each left out taking its default:
    ``temp_from`` and ``temp_to`` in C, ``rh_from`` and ``rh_to`` in %, for
    the comfortable ranges, and the same four with ``acceptable_`` before
    them for the acceptable ranges.

    Raises:
        ConfigError: an edge that is not a number, a range that ends where it
            starts or before, or a comfortable range outside its acceptable one.
    """
    boxes = {}
    for box in ("temp", "rh", "acceptable_temp", "acceptable_rh"):
        edges = []
        for end, default in zip(("from", "to"), getattr(COMFORT, box)):
            key = f"{box}_{end}"
            value = get_prop_by_keys(config, "comfort", key, default=default)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ConfigError(f"comfort.{key} must be a number")
            edges.append(float(value))
        if edges[0] >= edges[1]:
            raise ConfigError(f"comfort.{box}_to must be above comfort.{box}_from")
        boxes[box] = tuple(edges)
    c = Comfort(**boxes)
    for inner, outer in (("temp", "acceptable_temp"), ("rh", "acceptable_rh")):
        if getattr(c, outer)[0] > getattr(c, inner)[0]:
            raise ConfigError(f"comfort.{outer}_from must be at or below comfort.{inner}_from")
        if getattr(c, outer)[1] < getattr(c, inner)[1]:
            raise ConfigError(f"comfort.{outer}_to must be at or above comfort.{inner}_to")
    # A humid edge falls as the air warms; it must clear its dry edge at the
    # warm side too, where the warm edge meets the dry one.
    for which, (prefix, temps, dry) in enumerate((("", c.temp, c.rh[0]),
                                                  ("acceptable_", c.acceptable_temp,
                                                   c.acceptable_rh[0]))):
        if c.humid_above(temp_along_feel(temps[1], dry))[which] <= dry:
            raise ConfigError(f"comfort.{prefix}rh_to must be higher: at "
                              f"comfort.{prefix}temp_to its edge is below comfort.{prefix}rh_from")
    return c


def epd_config(config: dict) -> dict:
    """``config`` as epd reads it: without ``display.sync``, which is canary's
    own and which epd's display block would refuse."""
    display = config.get("display")
    if not isinstance(display, dict) or "sync" not in display:
        return config
    return {**config, "display": {k: v for k, v in display.items() if k != "sync"}}


def load_settings(config: dict) -> Settings:
    """The settings in ``config``, checked as the server checks them at start.

    Raises:
        ConfigError, KeyError, ValueError: the first problem, with a message
            for the person editing the file.
    """
    core = load_core_config(epd_config(config), default_display=DEFAULT_DISPLAY,
                            default_firmware_product="canary-display",
                            default_mqtt_prefix="mqtt/canary",
                            base_dir=cwd,
                            default_width=1280, default_height=720)
    kind = get_prop_by_keys(config, "source", "kind", default="mock")
    if kind not in SOURCE_KINDS:
        raise ConfigError(f"source.kind {kind!r} is not one of {', '.join(SOURCE_KINDS)}")
    if not isinstance(core.server.schedule, TimeRangesSchedule):
        raise ConfigError("display.schedule.type must be timeranges: canary changes the page "
                          "on ranges round the clock")
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
        store_path=str(get_prop_by_keys(config, "source", "path", default="data/sensor-readings.db")),
        keep_days=float(get_prop_by_keys(config, "source", "keep_days", default=0)),
        calibration_path=str(get_prop_by_keys(config, "calibration", "path",
                                              default="data/calibration.db")),
        calibration_days=float(get_prop_by_keys(config, "calibration", "keep_days", default=3)),
        status_path=str(get_prop_by_keys(config, "status", "path", default="data/status.db")),
        status_days=float(get_prop_by_keys(config, "status", "keep_days", default=7)),
        logs_path=str(get_prop_by_keys(config, "logs", "path", default="data/board-logs.db")),
        logs_days=float(get_prop_by_keys(config, "logs", "keep_days", default=7)),
        altitude_m=float(get_prop_by_keys(config, "site", "altitude_m", default=0)),
        comfort=load_comfort(config),
        dock_sync=make_dock_sync(config, core.server.timezone),
        display_sync=make_display_sync(config, core.server.timezone),
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


def store_file(path: str, base: str = cwd) -> str:
    """``path`` resolved against ``base``, with its folder made: SQLite makes
    the file but not the folder, and the stores default into ``data/``."""
    full = os.path.join(base, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    return full


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
    config_path = os.path.join(cwd, "config.yaml")
    with open(config_path) as f:
        running = config_version(f.read())
    config = load_yaml(config_path)

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

    # Served to the display, not listed: no page set or menu shows it.
    splash = SplashPage(logo_svg(), **core.image.page_kwargs())
    off_hours = OffHoursSchedule(core.server.schedule, splash.png_filename)
    schedule = AfterReadingSchedule(off_hours, core.server.regen_lead_seconds)
    status_store = ReadingsStore(store_file(settings.status_path))
    display_settings = display_version(config)
    reports = DeviceReports(store=status_store, keep_days=settings.status_days,
                            silence=make_silence(settings.syncs),
                            next_sync=make_next_sync(settings.syncs, schedule.page_wake),
                            stamps={DISPLAY: display_settings})
    log.info("board reports in %s, %d held", status_store.path, status_store.count())
    store = None
    if settings.kind == "store":
        store = ReadingsStore(store_file(settings.store_path))
        log.info("readings from %s, %d held", store.path, store.count())
    source = make_source(settings.seed, clock, reports, settings.altitude_m, store)
    calibration = CalibrationStore(store_file(settings.calibration_path),
                                   keep_days=settings.calibration_days)
    ingest = ReadingsIngest(reports, store, settings.keep_days)
    dock_sync = settings.dock_sync
    about = About(version, core.firmware,
                  syncs={"dock": settings.dock_sync, "display": settings.display_sync},
                  config=running)
    pages = make_pages(tz, settings.comfort, **core.image.page_kwargs())
    between = make_between(settings.seed, clock, store)
    history = HistoryQuery(make_history(between, settings.altitude_m), tz, now=clock,
                           comfort=settings.comfort)
    readings = ReadingsQuery(between, now=clock)
    status = StatusSource(reports)
    board_logs = LogStore(store_file(settings.logs_path), keep_days=settings.logs_days)
    logs = LogsQuery(board_logs, tz)
    board_settings = BoardSettings(settings.dock, dock_sync, calibration, reports.device, now=clock)
    display_sync = DisplaySync(display_settings, settings.display_sync, reports.device, now=clock)

    try:
        server = DisplayServer(
            pages=[*pages, splash],
            source=source,
            schedule=schedule,
            tz=tz,
            regen_lead_seconds=core.server.regen_lead_seconds,
            port=core.server.port,
            https_port=core.server.https_port,
            certificate_dir=CERTIFICATE_DIR,
            mqtt=core.mqtt,
            mqtt_client_id="canary-server",
            client_logs=board_logs,
            ingest={"sensor-readings": ingest.accept, "calibration": calibration.accept},
            queries={"calibration": calibration.answer, "about": about.answer,
                     "board-settings": board_settings.answer,
                     "history": history.answer, "sensor-readings": readings.answer,
                     "status": lambda args: status.status(), "logs": logs.answer},
            firmware=core.firmware,
            network=core.network,
            install_boards=INSTALL_BOARDS,
            settings_url="web/config",
            header_prefix="Canary",
            server_version=about.version,
            version_gate=True,
            sensor_poll=make_sensor_poll(settings.syncs, schedule.page_wake),
            on_refused=reports.refused,
        )
    except ValueError as exc:
        log.error(str(exc))
        sys.exit(1)
    splash_when_off(server.app, off_hours, [p.name for p in pages], splash.name, clock)
    server.app.register_blueprint(web_blueprint(pages, source, logging_on=core.mqtt.enabled))
    stores = {
        "sensor-readings": Transfer("sensor-readings", store_file(settings.store_path)),
        "board-reports": Transfer("board-reports", status_store.path),
        "calibration": Transfer("calibration", calibration.path, "calibration"),
        "board-logs": Transfer("board-logs", board_logs.path, "logs"),
    }
    server.app.register_blueprint(config_blueprint(pages, os.path.join(cwd, "config.yaml"),
                                                   check_config, restart_soon, stores,
                                                   dock=board_settings, display=display_sync,
                                                   boards=reports.device))

    if args.once or args.only:
        server.regenerate(only=args.only)
        return
    server.run()


if __name__ == "__main__":
    main()
