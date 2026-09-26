"""The config page's form: its tabs and fields, and what a filled-in form
does to config.yaml.

The file is edited with ruamel.yaml, which keeps its comments and layout, and
read with PyYAML, which is what the server starts on. The two read some plain
scalars differently (``01:00`` is a string to ruamel and a number to PyYAML),
so a string is written in quotes whenever PyYAML would read it as something
else, and every edit is read back with PyYAML before it is accepted.
"""
from __future__ import annotations

import io
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

import yaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import CommentMark
from ruamel.yaml.scalarstring import DoubleQuotedScalarString
from ruamel.yaml.tokens import CommentToken

import dock_settings as ds
from epd_server.timeranges import DAYS, MAX_RANGES
from schedule import DEFAULT_DOCK_WEEK, DEFAULT_HEAD_SYNC_S, DEFAULT_PAGE_WEEK

# A key the file does not have.
MISSING: Any = object()


@dataclass(frozen=True)
class Field:
    """One setting on the form.

    ``default`` is what the server takes when the key is absent, or a function
    of the config that gives it; the form shows it as the field's value.
    ``hint`` is an example of the value, for a field with no default. ``when``
    is another field and a
    value, as ``source.kind=store``, or values, as ``led.well.pattern=pulse|flash``:
    the field shows only while that one holds one of them. ``env`` is false for keys the server reads without looking for an
    environment variable.
    """
    key: str
    label: str
    help: str = ""
    kind: str = "text"      # text zone int number bool choice time window pools order week looks
    default: Any = None
    hint: str = ""
    choices: tuple[tuple[str, str], ...] = ()
    unit: str = ""
    minimum: float | None = None
    maximum: float | None = None
    step: int = 1
    when: str = ""
    env: bool = True
    long: str = ""          # the name in messages, when the label leans on its place on the page
    scale: int = 1          # the file's units in one of the input's: 60 shows seconds as minutes

    @property
    def path(self) -> tuple[str, ...]:
        return tuple(self.key.split("."))

    @property
    def env_name(self) -> str:
        return "_".join(self.path).upper()


    def env_value(self) -> str | None:
        """The environment variable that sets this key over the file, if one is set."""
        return os.environ.get(self.env_name) if self.env else None


@dataclass(frozen=True)
class Group:
    """``store`` names the store this group's file holds, for the export row.
    ``action`` names a row after the fields: ``recalibrate``, which acts at
    once rather than saving; ``position``, a grid that sets the group's two
    alignments together; or ``head``, the size the head reports. ``visual``
    names a drawing of the group's values that can also set them: ``dial``,
    the day's syncs, ``slot``, the time before one sync, ``panel``, the
    image and its drawn area. ``disk``, the space the stores take on the
    server's disk, only shows. ``caption`` says what the drawing shows, when
    the page's own words for it do not. ``about`` is the line under the
    heading that says what the group is for."""
    heading: str
    fields: tuple[Field, ...]
    store: str = ""
    action: str = ""
    visual: str = ""
    caption: str = ""
    about: str = ""


@dataclass(frozen=True)
class Tab:
    """``sheet`` sets the tab out as a spec sheet: each group under a rule,
    its heading in a column beside it, and each field a line with a dotted
    leader from its name to its value."""
    name: str
    title: str
    groups: tuple[Group, ...]
    sheet: bool = False

    @property
    def fields(self) -> list[Field]:
        return [f for g in self.groups for f in g.fields]


# The status light's triggers, as the Dock tab names them, in their order.
LED_TRIGGER_LABELS = {"starting": "Starting", "no_wifi": "No Wi-Fi", "post_failed": "Post failed",
                      "sensor_missing": "Sensor missing", "well": "Well"}
# The light's patterns, as the Dock tab names them.
LED_PATTERN_LABELS = {p: p.replace("_", " ").capitalize() for p in ds.LED_PATTERNS}


TABS: tuple[Tab, ...] = (
    Tab("server", "Server", (
        Group("Network", about="Where the boards and browsers reach the server", fields=(
            Field("server.port", "Port", "", "int", 8080, minimum=1, maximum=65535),
        )),
        Group("Pages", about="When the server draws each page", fields=(
            Field("server.regen_lead_seconds", "Pre-render pages", "Before each page change.", "int", 120,
                  unit="seconds", minimum=0),
        )),
        Group("Location", about="Where the device is, for its local time and sea-level pressure", fields=(
            Field("server.timezone", "Time zone", "", "zone", lambda cfg: host_zone()),
            Field("site.altitude_m", "Altitude", "", "number", 0, unit="m"),
        )),
        Group("Log", about="How much the server writes to its log", fields=(
            Field("debug", "Debug log", "", "bool", False),
        )),
    ), sheet=True),
    Tab("display", "Display", (
        Group("Page schedule", about="When to change to the next page", fields=(
            Field("display.schedule.week", "Page schedule",
                  "Each time range runs until the next one starts; 0 minutes = off.", "week",
                  DEFAULT_PAGE_WEEK, env=False),
            Field("display.schedule.order", "Order", "", "order", lambda cfg: pool_names(cfg),
                  env=False),
            Field("display.schedule.reshuffle_hours", "Reshuffle",
                  "Changes where each pool starts.", "number", 3, unit="hours", minimum=0,
                  env=False),
            Field("display.schedule.seed", "Seed", "", "int", 0, env=False),
        ), visual="dial", caption="Each tick is a page change. Hatching marks a time range "
                                  "that is off. Drag a time range's start to move it."),
        Group("Sync schedule", about="How often to update the server with its display state", fields=(
            Field("head.sync.every", "Every", "The head also syncs at each page. 0 = only then.",
                  "int", DEFAULT_HEAD_SYNC_S, unit="minutes", minimum=0, maximum=24 * 60,
                  scale=60, long="Sync every"),
        )),
        Group("Pools", about="The pages to show, in groups taken in turn", fields=(
            Field("display.pools", "Pools", "Drag to reorder.", "pools", env=False),
        )),
    ), sheet=True),
    Tab("image", "Image", (
        Group("Size", about="The size of the image the server draws for the panel", fields=(
            Field("image.width", "Width", "", "int", 1280, unit="px",
                  minimum=1),
            Field("image.height", "Height", "", "int", 720, unit="px",
                  minimum=1),
        ), action="head", visual="panel"),
        Group("Drawn area", about="The part of the image the pages are drawn in", fields=(
            Field("image.innerWidth", "Width", "", "int",
                  lambda cfg: effective(cfg, "image.width"), unit="px",
                  minimum=1),
            Field("image.innerHeight", "Height", "", "int",
                  lambda cfg: effective(cfg, "image.height"),
                  unit="px", minimum=1),
            Field("image.innerAlignX", "Across", "", "choice", "center",
                  choices=(("left", "Left"), ("center", "Centre"), ("right", "Right"))),
            Field("image.innerAlignY", "Up and down", "", "choice", "center",
                  choices=(("top", "Top"), ("center", "Centre"), ("bottom", "Bottom"))),
        ), action="position"),
    ), sheet=True),
    Tab("dock", "Dock", (
        Group("Sync schedule", about="How often to take a reading and update the server with it", fields=(
            Field("dock.sync.week", "Sync schedule",
                  "Each time range runs until the next one starts; 0 minutes = off.", "week",
                  DEFAULT_DOCK_WEEK, env=False),
        ), visual="dial", caption="Each tick is a sync and a reading. Hatching marks a time "
                                  "range that is off; the inner line, the light's schedule. "
                                  "Drag a time range's start to move it."),
        Group("Before each sync · PMSA003I", about="How long the fan runs before each reading", fields=(
            Field("dock.pm.warmup_s", "Fan warm-up", "0 = always on.", "int", ds.PM_WARMUP_S,
                  unit="seconds", minimum=0, maximum=ds.PM_WARMUP_MAX_S),
        ), visual="slot"),
        Group("CO₂ · SCD41", about="How the CO₂ sensor corrects its readings", fields=(
            Field("dock.scd41.temperature_offset_c", "Temperature offset",
                  "Heat from the dock, taken off the SCD41's reading.", "number",
                  ds.SCD41_OFFSET_C, unit="°C", minimum=0, maximum=ds.SCD41_OFFSET_MAX_C),
            Field("dock.scd41.self_calibration", "Self-calibration",
                  "Takes the lowest reading of each week as fresh air.", "bool", True),
        ), action="recalibrate"),
        Group("Humidity · SHTC3", about="How the humidity sensor measures", fields=(
            Field("dock.shtc3.low_power", "Low power", "Faster readings, less repeatable.",
                  "bool", False),
        )),
        Group("Air quality · BME688", about="How often BSEC samples the air-quality sensor", fields=(
            Field("dock.bsec.sample_s", "Sample", "A change starts IAQ learning again.", "choice",
                  300, choices=(("3", "Every 3 s"), ("300", "Every 5 min"))),
        )),
        Group("Status light", about="How the dock's light shows what it is doing", fields=(
            Field("dock.led.brightness_pct", "Brightness", "0 = off.", "int",
                  ds.LED_BRIGHTNESS_PCT, unit="%", minimum=0, maximum=100),
            Field("dock.led.schedule", "Schedule", "The hours the light is on. Off = all day.",
                  "window", False, env=False),
            Field("dock.led.schedule.from", "From", "", "time", when="dock.led.schedule=true",
                  env=False, long="Schedule from"),
            Field("dock.led.schedule.to", "To", "", "time", when="dock.led.schedule=true",
                  env=False, long="Schedule to"),
            Field("dock.led.looks", "Patterns",
                  "The first row whose trigger is true sets the light. A trigger with no row "
                  "is skipped. Length is one cycle of the pattern.", "looks",
                  ds.DEFAULT_LED_LOOKS, env=False),
        )),
        Group("Log", about="How much the dock writes to its log", fields=(
            Field("dock.log.level", "Level", "", "choice", "debug",
                  choices=tuple((level, level.capitalize()) for level in ds.LOG_LEVELS)),
        )),
    ), sheet=True),
    Tab("storage", "Storage", (
        Group("Disk", about="The space the files below take on the server's disk", fields=(),
              visual="disk"),
        Group("Sensor readings", about="The dock's readings, kept on the server", fields=(
            Field("source.path", "File", "", "text", "sensor-readings.db"),
            Field("source.keep_days", "Delete after", "0 = never.", "number", 0, unit="days",
                  minimum=0),
        ), store="sensor-readings"),
        Group("Board reports", about="What each board says about itself at each sync", fields=(
            Field("status.path", "File", "", "text", "status.db"),
            Field("status.keep_days", "Delete after", "0 = never.", "number", 7, unit="days",
                  minimum=0),
        ), store="board-reports"),
        Group("Board logs", about="What each board logs over MQTT", fields=(
            Field("logs.path", "File", "", "text", "board-logs.db"),
            Field("logs.keep_days", "Delete after", "0 = never.", "number", 7, unit="days",
                  minimum=0),
        ), store="board-logs"),
        Group("Calibration", about="Copies of the air-quality sensor's calibration, for after a restart", fields=(
            Field("calibration.path", "File", "", "text", "calibration.db"),
            Field("calibration.keep_days", "Delete after", "0 = never.", "number", 3, unit="days",
                  minimum=0),
        ), store="calibration"),
    ), sheet=True),
    Tab("firmware", "Firmware", (
        Group("Updates", about="Whether the server offers new firmware to the boards", fields=(
            Field("client.firmware.enabled", "Update boards", "", "bool", False),
            Field("client.firmware.dir", "Folder", "", "text", "firmware",
                  when="client.firmware.enabled=true"),
        )),
    ), sheet=True),
    Tab("mqtt", "MQTT", (
        Group("Board logs", about="What the boards log over MQTT, kept for the Logs page", fields=(
            Field("mqtt.enabled", "Keep logs", "", "bool", False),
            Field("mqtt.host", "Host", "", "text", "localhost", when="mqtt.enabled=true"),
            Field("mqtt.port", "Port", "", "int", 1883, minimum=1, maximum=65535,
                  when="mqtt.enabled=true"),
            Field("mqtt.prefix", "Prefix", "Each board logs to <prefix>/<board>.", "text",
                  "mqtt/canary", when="mqtt.enabled=true"),
        )),
    ), sheet=True),
)

FIELDS: tuple[Field, ...] = tuple(f for t in TABS for f in t.fields)
BY_KEY: dict[str, Field] = {f.key: f for f in FIELDS}
TAB_OF: dict[str, str] = {f.key: t.name for t in TABS for f in t.fields}


class FieldError(ValueError):
    """A value the form cannot write. The message is for the person filling it in."""


class FormError(ValueError):
    """The form cannot make this edit at all. The message says to use the YAML tab."""


# ── Reading ─────────────────────────────────────────────────────────

def read(text: str) -> dict:
    """``text`` as the server reads it.

    Raises:
        FormError: it is not YAML, or not a mapping.
    """
    try:
        cfg = yaml.safe_load(text)
    except yaml.YAMLError:
        raise FormError("Not valid YAML. Fix it in the YAML tab.")
    if cfg is None:
        return {}
    if not isinstance(cfg, dict):
        raise FormError("Top level is not a mapping. Fix it in the YAML tab.")
    return cfg


def lookup(cfg: Any, path: Iterable) -> Any:
    node = cfg
    for k in path:
        if not isinstance(node, dict) or k not in node:
            return MISSING
        node = node[k]
    return node


def host_zone() -> str:
    """The zone the server runs in when config.yaml names none."""
    tz = datetime.now().astimezone().tzinfo
    return str(getattr(tz, "key", "") or (tz.tzname(None) if tz else "") or "UTC")


def pool_names(cfg: dict) -> list[str]:
    pools = lookup(cfg, ("display", "pools"))
    return [str(n) for n in pools] if isinstance(pools, dict) else []


def default_of(f: Field, cfg: dict) -> Any:
    """What the server takes for ``f`` when config.yaml leaves it out."""
    return f.default(cfg) if callable(f.default) else f.default


def effective(cfg: dict, key: str) -> Any:
    """The value the server uses for ``key``: the file's, or the default."""
    v = lookup(cfg, BY_KEY[key].path)
    return default_of(BY_KEY[key], cfg) if v is MISSING else v


def _scaled(f: Field, value: Any) -> Any:
    """``value`` from the file in the input's units."""
    if f.scale == 1 or isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    shown = value / f.scale
    return int(shown) if shown == int(shown) else shown


def input_text(f: Field, value: Any) -> str:
    """A value from the file as ``f``'s input shows it."""
    return _as_input(_scaled(f, value))


def _as_input(value: Any) -> str:
    if value is None or value is MISSING:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(map(str, value))
    return str(value)


def _pool_rows(v: Any) -> list[tuple[str, str]]:
    if not isinstance(v, dict):
        return []
    return [(str(n), ", ".join(map(str, p if isinstance(p, list) else [p]))) for n, p in v.items()]


# The fields that are rows of inputs rather than one.
ROWS = ("pools", "week", "looks")
# Each day's name, short as a group's chip shows it, and whole.
DAY_SHORT = {d: d.capitalize() for d in DAYS}
DAY_LONG = dict(zip(DAYS, ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
                           "Sunday")))


def days_words(days) -> str:
    """"Every day", "Mon–Fri", "Sat–Sun", "Mon, Wed–Fri": a group's days,
    Monday first, a run of two or more joined by a dash."""
    picked = sorted({DAYS.index(d) for d in days if d in DAYS})
    if len(picked) == len(DAYS):
        return "Every day"
    runs: list[list[int]] = []
    for d in picked:
        if runs and runs[-1][-1] == d - 1:
            runs[-1].append(d)
        else:
            runs.append([d])
    return ", ".join(DAY_SHORT[DAYS[r[0]]] if len(r) == 1
                     else f"{DAY_SHORT[DAYS[r[0]]]}–{DAY_SHORT[DAYS[r[-1]]]}" for r in runs)
# The light's schedule, a window the form edits as one switch and two times.
LIGHT_KEY = "dock.led.schedule"
LIGHT_PATH = ("dock", "led", "schedule")


def _light_block(cfg: dict) -> dict | None:
    """The light's schedule when the file gives one; None when it is on all day."""
    d = lookup(cfg, LIGHT_PATH)
    return d if isinstance(d, dict) and d else None


def _clock_rows(v: Any) -> list[tuple[str, str]]:
    """A schedule's ranges as the form's rows: the start, and the interval in minutes."""
    if not isinstance(v, list):
        return []
    rows = []
    for r in v:
        if isinstance(r, dict):
            every = r.get("every", "")
            minutes = every // 60 if isinstance(every, int) and not isinstance(every, bool) \
                and every % 60 == 0 else every
            rows.append((str(r.get("from", "")), str(minutes)))
    return rows


def _week_rows(v: Any) -> list[tuple[str, list[tuple[str, str]]]]:
    """A week as the form's groups: the days, as "mon,tue", and the group's rows."""
    if not isinstance(v, list):
        return []
    return [(",".join(d for d in g["days"] if isinstance(d, str))
             if isinstance(g.get("days"), list) else "",
             _clock_rows(_in_order(g.get("ranges")))) for g in v if isinstance(g, dict)]


def _look_rows(v: Any) -> list[tuple[str, str, str]]:
    """The light's looks as the form's rows: the trigger, the pattern and the
    length in seconds, which off and solid still have, unseen."""
    if not isinstance(v, list):
        return []
    return [(str(r.get("trigger", "")), str(r.get("pattern", "")),
             str(r.get("length_s", ds.LED_STILL_LENGTH_S))) for r in v if isinstance(r, dict)]


def shown(cfg: dict) -> dict[str, Any]:
    """Each field's value as its input shows it: a string, or rows for the
    pools, a schedule's groups of days and their ranges, and the light's looks."""
    out: dict[str, Any] = {}
    light = _light_block(cfg)
    for f in FIELDS:
        v = lookup(cfg, f.path)
        if f.kind == "pools":
            out[f.key] = _pool_rows(v)
        elif f.kind == "week":
            out[f.key] = _week_rows(_week_in_order(default_of(f, cfg) if v is MISSING else v))
        elif f.kind == "looks":
            out[f.key] = _look_rows(_looks_in_order(default_of(f, cfg) if v is MISSING else v))
        elif f.kind == "window":
            out[f.key] = "true" if light is not None else "false"
        elif f.key.startswith(LIGHT_KEY + ".") and light is None:
            out[f.key] = ds.DEFAULT_LED_SCHEDULE[f.path[-1]]
        else:
            out[f.key] = _as_input(_scaled(f, default_of(f, cfg) if v is MISSING else v))
    return out


def defaults(cfg: dict) -> dict[str, str]:
    """Each field's default as its input shows it, for the fields that have one."""
    light = _light_block(cfg)
    out: dict[str, str] = {}
    for f in FIELDS:
        if f.kind in ROWS:
            continue
        if f.key.startswith(LIGHT_KEY + ".") and light is None:
            d: Any = ds.DEFAULT_LED_SCHEDULE[f.path[-1]]
        else:
            d = default_of(f, cfg)
        if d is not None:
            out[f.key] = _as_input(_scaled(f, d))
    return out



def submitted(form) -> dict[str, Any]:
    """The values a posted form holds, as :func:`shown` gives them."""
    out: dict[str, Any] = {}
    for f in FIELDS:
        if f.key not in form:
            continue
        if f.kind == "pools":
            out[f.key] = list(zip(form.getlist(f.key + ".name"), form.getlist(f.key + ".pages")))
        elif f.kind == "week":
            out[f.key] = _submitted_week(form, f.key)
        elif f.kind == "looks":
            out[f.key] = list(zip(form.getlist(f.key + ".trigger"), form.getlist(f.key + ".pattern"),
                                  form.getlist(f.key + ".length_s")))
        else:
            out[f.key] = form.getlist(f.key)[-1]
    return out


def _submitted_week(form, key: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """A week's groups as the form posts them: ``<key>.<n>.days``, and each
    row's ``<key>.<n>.from`` and ``<key>.<n>.every``, in the order of ``n``."""
    pattern = re.compile(re.escape(key) + r"\.(\d+)\.days")
    groups = sorted({int(m[1]) for k in form if (m := pattern.fullmatch(k))})
    return [(form.getlist(f"{key}.{n}.days")[-1],
             list(zip(form.getlist(f"{key}.{n}.from"), form.getlist(f"{key}.{n}.every"))))
            for n in groups]


def initial(value: Any) -> str:
    """A value as config.js compares it, to tell whether the field has changed."""
    if isinstance(value, list):
        return json.dumps([list(r) for r in value], separators=(",", ":"), ensure_ascii=False)
    return value


# ── Parsing ─────────────────────────────────────────────────────────

_HHMM = re.compile(r"(\d{1,2}):(\d{2})")
_HHMMSS = re.compile(r"(\d{1,2}):(\d{2})(?::(\d{2}))?")


def _bounds(f: Field, v: float) -> None:
    if f.minimum is not None and v < f.minimum:
        raise FieldError(f"Must be at least {f.minimum:g}.")
    if f.maximum is not None and v > f.maximum:
        raise FieldError(f"Must be at most {f.maximum:g}.")
    if f.step > 1 and v % f.step:
        raise FieldError(f"Must be a multiple of {f.step}.")


def _images(pages: str) -> list[str]:
    return [p.strip() for p in pages.split(",") if p.strip()]


def _parse_pools(rows) -> dict[str, list[str]]:
    pools: dict[str, list[str]] = {}
    for name, pages in rows:
        name, images = name.strip(), _images(pages)
        if not name and not images:
            continue
        if not name:
            raise FieldError("Each pool needs a name.")
        if name in pools:
            raise FieldError(f"Duplicate pool: {name}.")
        if not images:
            raise FieldError(f"{name} has no images.")
        pools[name] = images
    return pools


def _in_order(ranges: Any) -> Any:
    """A schedule's ranges from the earliest start, as the form writes them;
    anything else as it is."""
    if isinstance(ranges, list) and all(isinstance(r, dict) for r in ranges):
        return sorted(ranges, key=lambda r: str(r.get("from", "")))
    return ranges


def _week_in_order(week: Any) -> Any:
    """A week as the form writes it: each group's days Monday first and its
    ranges from the earliest start, the groups in the order of their first
    days; anything else as it is."""
    if not (isinstance(week, list) and all(isinstance(g, dict) for g in week)
            and all(isinstance(g.get("days"), list) and g["days"]
                    and all(d in DAYS for d in g["days"]) for g in week)):
        return week
    groups = [{**g, "days": sorted(g["days"], key=DAYS.index), "ranges": _in_order(g.get("ranges"))}
              for g in week]
    return sorted(groups, key=lambda g: DAYS.index(g["days"][0]))


def _parse_clock(rows) -> list[dict]:
    """A schedule's rows as its ranges, from the earliest start."""
    ranges: dict[str, int] = {}
    for at, every in rows:
        at, every = at.strip(), every.strip()
        if not at and not every:
            continue
        m = _HHMM.fullmatch(at)
        if not m or int(m[1]) > 23 or int(m[2]) > 59:
            raise FieldError(f"{at or 'A time range'}: not a time.")
        at = f"{int(m[1]):02d}:{m[2]}"
        try:
            minutes = int(every)
        except ValueError:
            raise FieldError(f"From {at}: enter a whole number of minutes.") from None
        if not 0 <= minutes <= 24 * 60:
            raise FieldError(f"From {at}: enter 0 to {24 * 60} minutes.")
        if at in ranges:
            raise FieldError(f"Two time ranges start at {at}.")
        ranges[at] = minutes * 60
    if not ranges:
        raise FieldError("Keep at least one time range.")
    if len(ranges) > MAX_RANGES:
        raise FieldError(f"At most {MAX_RANGES} time ranges.")
    return [{"from": at, "every": ranges[at]} for at in sorted(ranges)]


def _parse_week(groups) -> list[dict]:
    """A week's groups as config.yaml writes them, as :func:`_week_in_order`
    orders them. Each day must be in exactly one group."""
    week: list[dict] = []
    seen: set[str] = set()
    for text, rows in groups:
        days = [d.strip() for d in text.split(",") if d.strip()]
        if not days:
            raise FieldError("Each group needs at least one day.")
        unknown = [d for d in days if d not in DAYS]
        if unknown:
            raise FieldError(f"{unknown[0]}: not a day.")
        for d in days:
            if d in seen:
                raise FieldError(f"{DAY_LONG[d]} is in two groups.")
            seen.add(d)
        try:
            ranges = _parse_clock(rows)
        except FieldError as exc:
            if len(groups) == 1:
                raise
            raise FieldError(f"{days_words(days)}: {exc}") from None
        week.append({"days": sorted(days, key=DAYS.index), "ranges": ranges})
    missing = [d for d in DAYS if d not in seen]
    if missing:
        raise FieldError(f"{days_words(missing)}: in no group. Each day needs one.")
    return sorted(week, key=lambda g: DAYS.index(g["days"][0]))


def _looks_in_order(looks: Any) -> Any:
    """The light's looks in the triggers' order, as the form writes them;
    anything else as it is."""
    if isinstance(looks, list) and all(isinstance(r, dict) for r in looks):
        rank = {t: i for i, t in enumerate(ds.LED_TRIGGERS)}
        return sorted(looks, key=lambda r: rank.get(r.get("trigger"), len(rank)))
    return looks


def _normal_looks(looks: Any) -> Any:
    """The looks in order, without the length of off or solid, which the dock
    does not use."""
    looks = _looks_in_order(looks)
    if not isinstance(looks, list):
        return looks
    return [{k: v for k, v in r.items() if k != "length_s" or r.get("pattern") not in ds.LED_STILL}
            for r in looks]


def _parse_looks(rows) -> list[dict]:
    """The light's rows as its looks, in the triggers' order. Off and solid
    are written without a length."""
    looks: dict[str, dict] = {}
    for trigger, pattern, length in rows:
        trigger, pattern, length = trigger.strip(), pattern.strip(), length.strip()
        label = LED_TRIGGER_LABELS.get(trigger)
        if label is None:
            raise FieldError("Choose a trigger for each row.")
        if trigger in looks:
            raise FieldError(f"Two rows for {label}.")
        if pattern not in ds.LED_PATTERNS:
            raise FieldError(f"{label}: choose a pattern.")
        look: dict[str, Any] = {"trigger": trigger, "pattern": pattern}
        if pattern not in ds.LED_STILL:
            try:
                seconds = float(length)
            except ValueError:
                raise FieldError(f"{label}: enter a length in seconds.") from None
            shortest = ds.led_min_length(pattern)
            if not shortest <= seconds <= ds.LED_LENGTH_MAX_S:
                raise FieldError(f"{label}: enter {shortest:g} to {ds.LED_LENGTH_MAX_S:g} "
                                 f"seconds for a {LED_PATTERN_LABELS[pattern].lower()}.")
            look["length_s"] = int(seconds) if seconds.is_integer() else seconds
        looks[trigger] = look
    return [looks[t] for t in ds.LED_TRIGGERS if t in looks]


def parse(f: Field, raw: Any) -> Any:
    """The value to write for what the input holds; None takes the key out,
    so the server uses its default."""
    if f.kind == "pools":
        return _parse_pools(raw)
    if f.kind == "week":
        return _parse_week(raw)
    if f.kind == "looks":
        return _parse_looks(raw)
    raw = str(raw).strip()
    if f.kind in ("bool", "window"):
        return raw == "true"
    if raw == "":
        return None
    if f.kind == "int":
        try:
            v = int(raw)
        except ValueError:
            raise FieldError("Must be a whole number.") from None
        _bounds(f, v)
        return v * f.scale
    if f.kind == "number":
        try:
            v = int(raw)
        except ValueError:
            try:
                v = float(raw)
            except ValueError:
                raise FieldError("Must be a number.") from None
            if not math.isfinite(v):
                raise FieldError("Must be a number.")
        _bounds(f, v)
        return v
    if f.kind == "choice":
        if raw not in [c for c, _ in f.choices]:
            raise FieldError("Must be one of " + ", ".join(w for _, w in f.choices) + ".")
        return int(raw) if raw.isdigit() else raw
    if f.kind == "time":
        m = _HHMM.fullmatch(raw)
        if not m or int(m[1]) > 23 or int(m[2]) > 59:
            raise FieldError("Must be HH:MM.")
        return f"{int(m[1]):02d}:{m[2]}"
    if f.kind == "order":
        return _images(raw)
    return raw


def _same(a: Any, b: Any) -> bool:
    """Whether the file's value ``a`` already says ``b``: a number is not the
    string of its digits, nor is true 1."""
    if a is MISSING:
        return False
    return (isinstance(a, bool) == isinstance(b, bool) and isinstance(a, str) == isinstance(b, str)
            and a == b)


# ── Writing ─────────────────────────────────────────────────────────

def _plain(s: str) -> bool:
    """Whether PyYAML reads ``s``, unquoted, as the same string. A time of
    day is quoted anyway: 1:00 unquoted is a number of minutes."""
    if _HHMMSS.fullmatch(s):
        return False
    try:
        return yaml.safe_load(s) == s
    except yaml.YAMLError:
        return False


def _node(value: Any) -> Any:
    """``value`` as ruamel writes it: strings quoted when they must be, lists
    on one line, mappings as blocks, and a list of mappings one to a line."""
    if isinstance(value, str):
        return value if _plain(value) else DoubleQuotedScalarString(value)
    if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
        seq = CommentedSeq()
        for v in value:
            item = CommentedMap((_node(k), _node(x)) for k, x in v.items())
            # One that holds a list of mappings, as a group of days holds its
            # ranges, is a block, so those stay one to a line.
            if not any(_is_mapping_list(x) for x in v.values()):
                item.fa.set_flow_style()
            seq.append(item)
        return seq
    if isinstance(value, list):
        seq = CommentedSeq(_node(v) for v in value)
        seq.fa.set_flow_style()
        return seq
    if isinstance(value, dict):
        m = CommentedMap((_node(k), _node(v)) for k, v in value.items())
        if not value:
            m.fa.set_flow_style()
        return m
    return value


def _is_mapping_list(v: Any) -> bool:
    return isinstance(v, list) and bool(v) and all(isinstance(x, dict) for x in v)


def _is_block(v: Any) -> bool:
    return isinstance(v, CommentedMap) and len(v) > 0 and not v.fa.flow_style()


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


# ruamel keeps the comment after a key as one token: the rest of the key's
# line, then every line up to the next key. A key with a block mapping under
# it has its token on its own line, and the lines after the block hang off
# the block's last key. These helpers move those lines when a key comes or
# goes, so a comment stays beside what it describes.

def _end(m: CommentedMap, key: Any) -> tuple[CommentedMap, Any]:
    """The mapping and key whose token holds the lines after ``m[key]`` and all under it."""
    while _is_block(m[key]):
        m = m[key]
        key = next(reversed(m))
    return m, key


def _after(m: CommentedMap, key: Any) -> str:
    item = m.ca.items.get(key)
    tok = item[2] if item and len(item) > 2 else None
    return tok.value.partition("\n")[2] if tok is not None else ""


def _set_after(m: CommentedMap, key: Any, lines: str) -> None:
    item = m.ca.items.get(key)
    tok = item[2] if item and len(item) > 2 else None
    if tok is not None:
        tok.value = tok.value.partition("\n")[0] + "\n" + lines
    elif lines:
        m.ca.items.setdefault(key, [None, None, None, None])[2] = CommentToken(
            "\n" + lines, CommentMark(0), None)


def _split(lines: str, indent: int) -> tuple[str, str]:
    """``lines`` in two at the first blank line or the first one indented
    less than ``indent``: what belongs with the entry, and what comes after
    the mapping it is in."""
    parts = lines.splitlines(keepends=True)
    for i, line in enumerate(parts):
        if not line.strip() or _indent_of(line) < indent:
            return "".join(parts[:i]), "".join(parts[i:])
    return lines, ""


def _outside(lines: str, indent: int) -> str:
    """The lines that outlive an entry at ``indent``: blanks, and comments no deeper than it."""
    return "".join(ln for ln in lines.splitlines(keepends=True)
                   if not ln.strip() or _indent_of(ln) <= indent)


def _join(a: str, b: str) -> str:
    """``a`` then ``b``, without adding to the blank lines where they meet."""
    head, tail = a.splitlines(keepends=True), b.splitlines(keepends=True)
    while head and tail and not head[-1].strip() and not tail[0].strip():
        tail.pop(0)
    return "".join(head + tail)


def _yaml(indent: int = 2, offset: int = 0) -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=indent, sequence=indent + offset, offset=offset)
    return y


_KEY_LINE = re.compile(r"( *)[^ #\-][^:#]*:(\s|$)")
_DASH_LINE = re.compile(r"( *)- ")


def _indents(text: str) -> tuple[int, int]:
    """How far ``text`` indents a mapping under its key, and a list's dash
    past its key: 2 and 2 when the file has no example of either.

    ruamel's own guess takes both from the first list it meets, which says
    nothing of how the mappings are indented."""
    mapping, offset, key_at = None, None, None
    for line in text.splitlines():
        key, dash = _KEY_LINE.match(line), _DASH_LINE.match(line)
        if key:
            at = len(key[1])
            if key_at is not None and at > key_at and mapping is None:
                mapping = at - key_at
            key_at = at
        elif dash and key_at is not None and offset is None:
            offset = len(dash[1]) - key_at
    return mapping or 2, offset if offset is not None and offset >= 0 else 2


class Doc:
    """config.yaml as ruamel holds it, with edits that keep its comments."""

    def __init__(self, text: str):
        if text.strip():
            self.ind, self.offset = _indents(text)
            try:
                root = _yaml(self.ind, self.offset).load(text)
            except Exception:  # noqa: BLE001 - any ruamel failure means the form cannot edit it
                raise FormError("Not valid YAML. Fix it in the YAML tab.") from None
        else:
            root, self.ind, self.offset = None, 2, 2
        if root is None:
            root = CommentedMap()
        if not isinstance(root, CommentedMap):
            raise FormError("Top level is not a mapping. Fix it in the YAML tab.")
        self.root = root

    def text(self) -> str:
        out = io.StringIO()
        _yaml(self.ind, self.offset).dump(self.root, out)
        return out.getvalue()

    def _chain(self, path) -> list[tuple[CommentedMap, int]]:
        """The mappings along ``path``'s parents with their depths, as far as they go."""
        chain = [(self.root, 0)]
        for depth, k in enumerate(path[:-1], start=1):
            v = chain[-1][0].get(k)
            if not isinstance(v, CommentedMap):
                break
            chain.append((v, depth))
        return chain

    def get(self, path) -> Any:
        return lookup(self.root, path)

    def set(self, path, value: Any) -> None:
        node = _node(value)
        m, depth = self.root, 0
        unflowed = None
        for i, k in enumerate(path[:-1]):
            v = m.get(k)
            if isinstance(v, CommentedMap):
                if v.fa.flow_style():
                    # {} becoming a block: the lines after its key go after the block.
                    unflowed = (m, k, _after(m, k))
                    _set_after(m, k, "")
                    v.fa.set_block_style()
                m, depth = v, depth + 1
                continue
            for j in reversed(path[i + 1:]):
                node = CommentedMap([(_node(j), node)])
            path = path[:i + 1]
            break
        key = path[-1]
        if key in m:
            self._replace(m, depth, key, node)
        else:
            self._append(m, depth, _node(key), node)
        if unflowed:
            um, uk, lines = unflowed
            em, ek = _end(um, uk)
            _set_after(em, ek, _after(em, ek) + lines)

    def _append(self, m: CommentedMap, depth: int, key: Any, node: Any) -> None:
        moved = ""
        if len(m):
            em, ek = _end(m, next(reversed(m)))
            keep, moved = _split(_after(em, ek), self.ind * depth)
            if depth == 0:
                keep += "\n"
            _set_after(em, ek, keep)
        m.ca.items.pop(key, None)
        m[key] = node
        if moved:
            em, ek = _end(m, key)
            _set_after(em, ek, _after(em, ek) + moved)

    def _replace(self, m: CommentedMap, depth: int, key: Any, node: Any) -> None:
        if not _is_block(m[key]) and not _is_block(node):
            m[key] = node
            return
        em, ek = _end(m, key)
        lines = _after(em, ek)
        if _is_block(m[key]):
            lines = _outside(lines, self.ind * depth)
            _set_after(m, key, "")
        _set_after(em, ek, "")
        m[key] = node
        em, ek = _end(m, key)
        _set_after(em, ek, _after(em, ek) + lines)

    def _delete(self, m: CommentedMap, depth: int, key: Any, carried: str = "") -> str:
        """Take ``key`` out of ``m``. The lines after it move to the entry
        before it; with none before it, they are handed back."""
        keys = list(m)
        i = keys.index(key)
        em, ek = _end(m, key)
        own = _after(m, key) if em is not m else ""
        lines = _outside(own + _after(em, ek) + carried, self.ind * depth)
        del m[key]
        m.ca.items.pop(key, None)
        if i > 0 and lines:
            pm, pk = _end(m, keys[i - 1])
            _set_after(pm, pk, _join(_after(pm, pk), lines))
            return ""
        return lines

    def remove(self, path) -> bool:
        """Take the key at ``path`` out, and any mapping that leaves empty."""
        chain = self._chain(path)
        if len(chain) < len(path):
            return False
        m, depth = chain[-1]
        if path[-1] not in m:
            return False
        carried = self._delete(m, depth, path[-1])
        level = len(path) - 1
        while level > 0 and not len(chain[level][0]):
            parent, pdepth = chain[level - 1]
            carried = self._delete(parent, pdepth, path[level - 1], carried)
            level -= 1
        if carried and level > 0:
            parent = chain[level - 1][0]
            _set_after(parent, path[level - 1], _join(_after(parent, path[level - 1]), carried))
        return True

    def set_pools(self, pools: dict[str, list[str]]) -> None:
        pm = self.get(("display", "pools"))
        if not isinstance(pm, CommentedMap) or not len(pm):
            self.set(("display", "pools"), pools)
            return
        if pm.fa.flow_style():
            pm.fa.set_block_style()
        keys = {str(k): k for k in pm}
        for name, images in pools.items():
            if name not in keys:
                self._append(pm, 2, _node(name), _node(images))
                keys[name] = name
            elif isinstance(pm[keys[name]], CommentedSeq):
                if list(pm[keys[name]]) != images:
                    pm[keys[name]][:] = [_node(i) for i in images]
            else:
                self._replace(pm, 2, keys[name], _node(images))
        for name, k in list(keys.items()):
            if name not in pools:
                self.remove(("display", "pools", k))
                del keys[name]
        if [str(k) for k in pm] != list(pools):
            em, ek = _end(pm, next(reversed(pm)))
            keep, moved = _split(_after(em, ek), self.ind * 2)
            _set_after(em, ek, keep)
            for name in pools:
                pm.move_to_end(keys[name])
            em, ek = _end(pm, next(reversed(pm)))
            _set_after(em, ek, _after(em, ek) + moved)


# ── Applying a form ─────────────────────────────────────────────────

@dataclass
class Edit:
    """What a posted form does to config.yaml."""
    text: str
    errors: dict[str, str]      # a field's key, and what is wrong with its value
    changed: list[str]          # the fields it changes


def _normal_pools(v: Any) -> list[tuple[str, list]]:
    if not isinstance(v, dict):
        return []
    return [(str(n), p if isinstance(p, list) else [p]) for n, p in v.items()]


def apply(text: str, form) -> Edit:
    """config.yaml as ``text`` with the values ``form`` posts, and what they change.

    A field the form leaves out stays as it is, and so does one an
    environment variable sets. An empty field takes its key out, bar the
    token, which stays until the YAML tab takes it out.

    Raises:
        FormError: the file cannot be edited this way, or the edit would not
            read back as the form gave it.
    """
    cfg = read(text)
    rows = submitted(form)
    values: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for f in FIELDS:
        if f.key not in form or f.env_value() is not None:
            continue
        raw = rows[f.key] if f.kind in ROWS else form.getlist(f.key)[-1]
        try:
            values[f.key] = parse(f, raw)
        except FieldError as exc:
            errors[f.key] = str(exc)
    if errors:
        return Edit(text, errors, [])

    doc = Doc(text)
    changed: list[str] = []
    expect: dict[tuple, Any] = {}

    def put(path, value) -> None:
        doc.set(path, value)
        expect[tuple(path)] = value

    def take(key: str) -> None:
        if doc.remove(BY_KEY[key].path if key in BY_KEY else tuple(key.split("."))):
            changed.append(key)
            expect[tuple(key.split("."))] = MISSING

    for f in FIELDS:
        if f.key not in values or f.key.startswith(LIGHT_KEY):
            continue
        value = values[f.key]
        if f.kind == "pools":
            if not value:
                if lookup(cfg, f.path) is not MISSING:
                    errors[f.key] = "Add at least one pool."
                continue
            if _normal_pools(lookup(cfg, f.path)) != list(value.items()):
                doc.set_pools(value)
                expect[f.path] = value
                changed.append(f.key)
        elif f.kind == "week":
            cur = lookup(cfg, f.path)
            if not _same(_week_in_order(cur), value) and not (cur is MISSING
                                                              and value == default_of(f, cfg)):
                put(f.path, value)
                changed.append(f.key)
        elif f.kind == "looks":
            cur = lookup(cfg, f.path)
            if not _same(_normal_looks(cur), value) and not (
                    cur is MISSING and value == _normal_looks(default_of(f, cfg))):
                put(f.path, value)
                changed.append(f.key)
        else:
            cur = lookup(cfg, f.path)
            if value is None:
                if cur is not MISSING:
                    take(f.key)
            elif not _same(cur, value) and not (cur is MISSING
                                                 and _same(default_of(f, cfg), value)):
                put(f.path, value)
                changed.append(f.key)

    if errors:
        return Edit(text, errors, [])

    if LIGHT_KEY in values:
        changed += _apply_light(cfg, values, put)

    if not changed:
        return Edit(text, {}, [])
    new_text = doc.text()
    _check_reads_back(cfg, new_text, changed, expect)
    return Edit(new_text, {}, changed)


def _apply_light(cfg: dict, values: dict, put) -> list[str]:
    """The light's schedule: ``{}`` when it is off, otherwise a block of the
    times the form gives, or the file's, or the defaults."""
    cur = _light_block(cfg)
    if not values[LIGHT_KEY]:
        if cur is None:
            return []
        put(LIGHT_PATH, {})
        return [LIGHT_KEY]
    block = {}
    for k in ("from", "to"):
        given = values.get(f"{LIGHT_KEY}.{k}")
        block[k] = given or (cur or {}).get(k) or ds.DEFAULT_LED_SCHEDULE[k]
    if _same(cur, block):
        return []
    put(LIGHT_PATH, block)
    return [LIGHT_KEY]


def _flat(d: Any, prefix: tuple = ()) -> dict[tuple, Any]:
    if not isinstance(d, dict) or (not d and prefix):
        return {prefix: d}
    out: dict[tuple, Any] = {}
    for k, v in d.items():
        out.update(_flat(v, prefix + (str(k),)))
    return out


def _changed_paths(old: dict, new: dict) -> list[tuple]:
    a, b = _flat(old), _flat(new)
    return [p for p in dict.fromkeys([*a, *b])
            if not (p in a and p in b and _same(a[p], b[p]))]


def _reads_as(got: Any, value: Any) -> bool:
    if value is MISSING:
        return got is MISSING
    if isinstance(value, dict):
        return (isinstance(got, dict) and [str(k) for k in got] == list(value)
                and not _changed_paths(got, value))
    return _same(got, value)


def _check_reads_back(cfg: dict, text: str, changed: list[str], expect: dict) -> None:
    """Refuse an edit that PyYAML would not read as the form gave it, or
    that touched a key the form did not change."""
    new = read(text)
    allowed = [tuple(k.split(".")) for k in changed]
    for path in _changed_paths(cfg, new):
        if not any(path[:len(p)] == p or p[:len(path)] == path for p in allowed):
            raise FormError(f"This edit also changes {name_of(path)}. Edit it in the YAML tab.")
    for path, value in expect.items():
        if not _reads_as(lookup(new, path), value):
            raise FormError(f"The form cannot save {name_of(path)} as entered. "
                            f"Edit it in the YAML tab.")


# ── Words for the page ──────────────────────────────────────────────

def field_at(path: tuple) -> Field | None:
    """The field that holds ``path``, or holds the mapping it is in."""
    best = None
    for f in FIELDS:
        if path[:len(f.path)] == f.path and (best is None or len(f.path) > len(best.path)):
            best = f
    return best


def locate(message: str) -> tuple[str | None, str | None]:
    """The field and the tab a problem from load_settings is about, as far
    as the key it starts with says."""
    head = tuple(message.split(" ", 1)[0].rstrip(":,.").split("."))
    f = field_at(head)
    if f is not None:
        return f.key, TAB_OF[f.key]
    for n in range(len(head), 0, -1):
        for t in TABS:
            if any(f.path[:n] == head[:n] for f in t.fields):
                return None, t.name
    return None, None


def name_of(path: tuple) -> str:
    f = field_at(path)
    if f is None:
        return ".".join(path)
    tab = next(t for t in TABS if t.name == TAB_OF[f.key])
    group = next(g for g in tab.groups if f in g.fields)
    name = f.long or f.label
    shared = sum((o.long or o.label) == name for o in tab.fields) > 1
    rest = path[len(f.path):]
    return " · ".join([tab.title, *([group.heading] if shared else []), name, *rest])


def _words(v: Any) -> str:
    if v is MISSING:
        return "not set"
    if isinstance(v, bool):
        return "on" if v else "off"
    if isinstance(v, list):
        return ", ".join(map(str, v))
    if v == {}:
        return "off"
    return str(v)


def _unit_words(f: Field, v: Any) -> Any:
    """A scaled field's value in the input's units, with them, as "5 minutes"."""
    shown = _scaled(f, v)
    return f"{shown} {f.unit}" if shown is not v else v


def _every_words(every: Any) -> str:
    if every == 0:
        return "off"
    if isinstance(every, int) and every % 60 == 0:
        return f"every {every // 60} min"
    return f"every {every} s"


def _clock_words(v: Any) -> str:
    """A day's ranges as "07:00 every 5 min · 01:00 every 30 min"."""
    if not isinstance(v, list):
        return _words(v)
    return " · ".join(f"{r.get('from', '?')} {_every_words(r.get('every'))}"
                      if isinstance(r, dict) else str(r) for r in v)


def _week_words(v: Any) -> str:
    """A week as "Mon–Fri: 07:00 every 5 min · 23:00 off; Sat–Sun: 09:00
    every 10 min", or a day's ranges alone when every day has them."""
    if not isinstance(v, list) or not all(isinstance(g, dict) for g in v):
        return _words(v)
    if len(v) == 1 and days_words(v[0].get("days") or []) == "Every day":
        return _clock_words(v[0].get("ranges"))
    return "; ".join(f"{days_words(g.get('days') or [])}: {_clock_words(g.get('ranges'))}"
                     for g in v)


def _seconds(v: Any) -> str:
    return f"{v:g}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)


def _look_words(v: Any) -> str:
    """The light's looks as "No Wi-Fi triple flash 1.9 s · Well solid"."""
    if not isinstance(v, list):
        return _words(v)
    if not v:
        return "none"
    return " · ".join(
        " ".join([LED_TRIGGER_LABELS.get(r.get("trigger"), str(r.get("trigger"))),
                  LED_PATTERN_LABELS.get(r.get("pattern"), str(r.get("pattern"))).lower(),
                  *([f"{_seconds(r['length_s'])} s"] if "length_s" in r else [])])
        if isinstance(r, dict) else str(r) for r in v)


def _with_words(cfg: dict) -> dict:
    """``cfg`` with the dock's sync schedule, the page schedule, and the
    light's schedule and looks each one setting in words, so a change to any
    reads as one line."""
    dock = cfg.get("dock")
    dock = dict(dock) if isinstance(dock, dict) else {}
    led = dock.get("led")
    led = dict(led) if isinstance(led, dict) else {}
    light = _light_block(cfg)
    led["schedule"] = f"{light.get('from', '?')}–{light.get('to', '?')}" if light else "all day"
    led["looks"] = _look_words(_normal_looks(effective(cfg, "dock.led.looks")))
    dock["led"] = led
    sync = dock.get("sync")
    sync = dict(sync) if isinstance(sync, dict) else {}
    sync["week"] = _week_words(_week_in_order(effective(cfg, "dock.sync.week")))
    dock["sync"] = sync
    display = cfg.get("display")
    display = dict(display) if isinstance(display, dict) else {}
    schedule = display.get("schedule")
    schedule = dict(schedule) if isinstance(schedule, dict) else {}
    schedule["week"] = _week_words(_week_in_order(effective(cfg, "display.schedule.week")))
    display["schedule"] = schedule
    return {**cfg, "dock": dock, "display": display}


def changes(old: dict, new: dict) -> list[dict[str, str]]:
    """Each setting that differs from ``old`` to ``new``, in words, in the form's order."""
    old, new = _with_words(old), _with_words(new)
    a, b = _flat(old), _flat(new)
    order = {f.key: i for i, f in enumerate(FIELDS)}
    out = []
    for path in _changed_paths(old, new):
        f = field_at(path)
        before, after = a.get(path, MISSING), b.get(path, MISSING)
        if f is not None and f.kind == "pools":
            before = "none" if before is MISSING else before
            after = "none" if after is MISSING else after
        if f is not None and f.scale != 1:
            before, after = (_unit_words(f, v) for v in (before, after))
        out.append((order.get(f.key, len(order)) if f else len(order),
                    {"name": name_of(path), "old": _words(before), "new": _words(after)}))
    return [c for _, c in sorted(out, key=lambda x: x[0])]
