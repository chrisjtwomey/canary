"""What the dock does between readings, from config.yaml's ``dock`` block.

The dock asks ``GET /board-settings?device=canary-dock`` before each reading
and applies what has changed. The answer is the settings, a version that
changes whenever they do, and two things that are not settings: whether the
light is dark until the next reading, and a recalibration waiting to run.

    {"version": "3f2a9c1e",
     "pm": {"warmup_s": 35},
     "scd41": {"temperature_offset_c": 4.0, "self_calibration": true},
     "shtc3": {"low_power": false},
     "led": {"brightness_pct": 15, "dark": false,
             "looks": [{"trigger": "starting", "pattern": "pulse", "length_s": 0.5}, ...]},
     "log": {"level": "debug"},
     "bsec": {"sample_s": 300},
     "recalibrate": {"id": 1758650400, "ppm": 420}}

The dock reports what it applied in its client status's ``dock`` block, as
``settings`` with the version and any keys it refused, and its last
recalibration as ``recalibrated``.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, time as clock_time
from typing import Any, Callable

from epd_server.config import ConfigError, get_prop_by_keys

from epd_server.timeranges import Week, in_window, parse_hhmm

DOCK = "canary-dock"

# The PM module settles in 30 s (Plantower); 35 leaves a margin for a slot the
# loop reaches late. A warm-up at or past the interval keeps the fan on.
PM_WARMUP_S = 35
PM_WARMUP_MIN_S = 30
PM_WARMUP_MAX_S = 600
# The SCD41's own default, and the range the datasheet recommends (3.6.1).
SCD41_OFFSET_C = 4.0
SCD41_OFFSET_MAX_C = 20.0
# The light's full brightness when it was set by eye on the bench.
LED_BRIGHTNESS_PCT = 15
# The light's triggers: the states the dock can be in, highest first. The
# dock shows the first that holds and has a look, and none of them when none
# does; its update has a look of its own that no setting changes.
LED_TRIGGERS = ("starting", "no_wifi", "post_failed", "sensor_missing", "well")
# The patterns, in the order the Dock tab offers them. A pattern repeats
# every length_s; a double or a triple is two or three flashes or quick
# pulses of 0.3 s each, then dark for the rest of the length.
LED_PATTERNS = ("off", "solid", "pulse", "double_pulse", "triple_pulse",
                "flash", "double_flash", "triple_flash")
# The patterns that hold one level, and so have no length.
LED_STILL = ("off", "solid")
# Each trigger's look by default, in the triggers' order.
LED_LOOKS = (("starting", "pulse", 0.5), ("no_wifi", "flash", 1),
             ("post_failed", "flash", 2), ("sensor_missing", "flash", 3),
             ("well", "pulse", 1))
DEFAULT_LED_LOOKS = [{"trigger": t, "pattern": p, "length_s": n} for t, p, n in LED_LOOKS]
LED_LENGTH_MIN_S = 0.25
LED_LENGTH_MAX_S = 10.0
# A double's or a triple's group and a dark gap of one of its steps, as the
# dock's StatusLed::minLengthMs has them.
LED_GROUP_MIN_S = {"double_pulse": 0.9, "triple_pulse": 1.2,
                   "double_flash": 0.9, "triple_flash": 1.2}
# The length the dock is sent for a pattern that has none.
LED_STILL_LENGTH_S = 1


def led_min_length(pattern: str) -> float:
    """The shortest length_s a pattern can have."""
    return LED_GROUP_MIN_S.get(pattern, LED_LENGTH_MIN_S)
# The window the form offers when the light's schedule is turned on.
DEFAULT_LED_SCHEDULE = {"from": "07:00", "to": "01:00"}
LOG_LEVELS = ("error", "warning", "notice", "info", "debug")
# BSEC's two rates, in seconds between samples. At 300 Bosch counts the
# BME688's self-heating as negligible; a change starts IAQ learning again.
BSEC_SAMPLE_S = (3, 300)
# The datasheet gives no range for a forced recalibration's reference. 400 is
# the bottom of the part's measuring range; above 2000 is not air anyone
# would calibrate in.
RECALIBRATE_MIN_PPM = 400
RECALIBRATE_MAX_PPM = 2000
# A recalibration the dock has not run within this is dropped: the air it
# was meant for has gone.
RECALIBRATE_WITHIN_S = 3600


@dataclass(frozen=True)
class DockSettings:
    """The ``dock`` block, checked."""
    pm_warmup_s: int = PM_WARMUP_S
    scd41_temperature_offset_c: float = SCD41_OFFSET_C
    scd41_self_calibration: bool = True
    shtc3_low_power: bool = False
    led_brightness_pct: int = LED_BRIGHTNESS_PCT
    led_schedule: tuple[clock_time, clock_time] | None = None   # the hours the light is on
    log_level: str = "debug"
    bsec_sample_s: int = 300
    led_looks: tuple[tuple[str, str, float], ...] = LED_LOOKS   # (trigger, pattern, length_s)

    def document(self) -> dict:
        """The settings as the dock reads them, without the version."""
        return {
            "pm": {"warmup_s": self.pm_warmup_s},
            "scd41": {"temperature_offset_c": self.scd41_temperature_offset_c,
                      "self_calibration": self.scd41_self_calibration},
            "shtc3": {"low_power": self.shtc3_low_power},
            "led": {"brightness_pct": self.led_brightness_pct,
                    "looks": [{"trigger": trigger, "pattern": pattern, "length_s": length}
                              for trigger, pattern, length in self.led_looks]},
            "log": {"level": self.log_level},
            "bsec": {"sample_s": self.bsec_sample_s},
        }

    @property
    def version(self) -> str:
        """Eight hex digits that change whenever a setting does."""
        text = json.dumps(self.document(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha1(text.encode()).hexdigest()[:8]


def _get(config: dict, key: str, default):
    return get_prop_by_keys(config, "dock", *key.split("."), default=default)


def _int(config: dict, key: str, default: int, low: int, high: int) -> int:
    value = _get(config, key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ConfigError(f"dock.{key} must be a whole number from {low} to {high}, "
                          f"not {value!r}")
    return value


def _bool(config: dict, key: str, default: bool) -> bool:
    value = _get(config, key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"dock.{key} must be true or false, not {value!r}")
    return value


def _led_looks(config: dict) -> tuple[tuple[str, str, float], ...]:
    """``dock.led.looks``, a list of ``{trigger, pattern, length_s}``, in the
    triggers' order. Off and solid need no length."""
    value = _get(config, "led.looks", DEFAULT_LED_LOOKS)
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise ConfigError("dock.led.looks must be a list of looks, each {trigger, pattern, "
                          "length_s}, or [] for none")
    looks: dict[str, tuple[str, str, float]] = {}
    for look in value:
        if not {"trigger", "pattern"} <= set(look) <= {"trigger", "pattern", "length_s"}:
            raise ConfigError(f"dock.led.looks: each look has trigger, pattern and length_s, "
                              f"not {', '.join(map(str, look)) or 'nothing'}")
        trigger, pattern = look["trigger"], look["pattern"]
        if trigger not in LED_TRIGGERS:
            raise ConfigError(f"dock.led.looks: trigger must be one of {', '.join(LED_TRIGGERS)}, "
                              f"not {trigger!r}")
        if trigger in looks:
            raise ConfigError(f"dock.led.looks has two looks for {trigger}")
        if pattern not in LED_PATTERNS:
            raise ConfigError(f"dock.led.looks: {trigger}'s pattern must be one of "
                              f"{', '.join(LED_PATTERNS)}, not {pattern!r}")
        if pattern in LED_STILL:
            length = look.get("length_s", LED_STILL_LENGTH_S)
        elif "length_s" not in look:
            raise ConfigError(f"dock.led.looks: {trigger}'s {pattern} needs a length_s")
        else:
            length = look["length_s"]
        shortest = led_min_length(pattern)
        if isinstance(length, bool) or not isinstance(length, (int, float)) \
                or not shortest <= length <= LED_LENGTH_MAX_S:
            raise ConfigError(f"dock.led.looks: {trigger}'s length_s must be from {shortest:g} "
                              f"to {LED_LENGTH_MAX_S:g} for {pattern}, not {length!r}")
        looks[trigger] = (trigger, pattern, round(float(length), 3))
    return tuple(looks[t] for t in LED_TRIGGERS if t in looks)


def _window(config: dict, key: str) -> tuple[clock_time, clock_time] | None:
    """A ``{from, to}`` window as two times of day; None, for all day, when it
    is absent or ``{}``."""
    value = _get(config, key, {})
    if value == {}:
        return None
    if not isinstance(value, dict) or set(value) != {"from", "to"}:
        raise ConfigError(f"dock.{key} must be {{from: \"HH:MM\", to: \"HH:MM\"}}, or {{}} "
                          f"for all day, not {value!r}")
    try:
        start, end = parse_hhmm(value["from"]), parse_hhmm(value["to"])
    except ValueError as exc:
        raise ConfigError(f"dock.{key}: {exc}") from None
    if start == end:
        raise ConfigError(f"dock.{key} starts and ends at the same time")
    return start, end


def load_dock_settings(config: dict) -> DockSettings:
    """The ``dock`` block of ``config``, with a default for each key it lacks.

    Raises:
        ConfigError: a value is out of range or of the wrong kind, named by
            its key.
    """
    warmup = _int(config, "pm.warmup_s", PM_WARMUP_S, 0, PM_WARMUP_MAX_S)
    if 0 < warmup < PM_WARMUP_MIN_S:
        raise ConfigError(f"dock.pm.warmup_s must be 0, for a fan that never stops, or at "
                          f"least {PM_WARMUP_MIN_S}, not {warmup}")
    offset = _get(config, "scd41.temperature_offset_c", SCD41_OFFSET_C)
    if isinstance(offset, bool) or not isinstance(offset, (int, float)) \
            or not 0 <= offset <= SCD41_OFFSET_MAX_C:
        raise ConfigError(f"dock.scd41.temperature_offset_c must be from 0 to "
                          f"{SCD41_OFFSET_MAX_C:g}, not {offset!r}")
    rate = _get(config, "bsec.sample_s", 300)
    if isinstance(rate, bool) or rate not in BSEC_SAMPLE_S:
        raise ConfigError(f"dock.bsec.sample_s must be 3 or 300, not {rate!r}")
    level = _get(config, "log.level", "debug")
    if level not in LOG_LEVELS:
        raise ConfigError(f"dock.log.level must be one of {', '.join(LOG_LEVELS)}, "
                          f"not {level!r}")
    return DockSettings(
        pm_warmup_s=warmup,
        scd41_temperature_offset_c=round(float(offset), 2),
        scd41_self_calibration=_bool(config, "scd41.self_calibration", True),
        shtc3_low_power=_bool(config, "shtc3.low_power", False),
        led_brightness_pct=_int(config, "led.brightness_pct", LED_BRIGHTNESS_PCT, 0, 100),
        led_schedule=_window(config, "led.schedule"),
        log_level=level,
        bsec_sample_s=rate,
        led_looks=_led_looks(config),
    )


def check_ppm(ppm) -> int:
    """``ppm`` as a recalibration's reference.

    Raises:
        ValueError: it is not a whole number in Sensirion's range.
    """
    try:
        value = int(str(ppm).strip())
    except ValueError:
        raise ValueError("Enter a whole number of ppm.") from None
    if not RECALIBRATE_MIN_PPM <= value <= RECALIBRATE_MAX_PPM:
        raise ValueError(f"Enter a value from {RECALIBRATE_MIN_PPM} to "
                         f"{RECALIBRATE_MAX_PPM} ppm.")
    return value


class BoardSettings:
    """The answer to ``GET /board-settings``, and what the Config page says
    about it.

    Args:
        settings: the ``dock`` block.
        sync: the dock's sync schedule, for its next slot.
        requests: where a recalibration waits; see CalibrationStore.
        reported: what the server knows of a device, as DeviceReports.device
            gives it, or None.
        now: the clock, for tests.
    """

    def __init__(self, settings: DockSettings, sync: Week, requests,
                 reported: Callable[[str], dict | None],
                 now: Callable[[], float] = time.time):
        self.settings = settings
        self.sync = sync
        self.requests = requests
        self.reported = reported
        self.now = now

    def answer(self, args: dict) -> dict:
        """The GET /board-settings handler.

        Raises:
            ValueError: the query names no device, or one with no settings.
        """
        device = args.get("device")
        if not device:
            raise ValueError("device is required")
        if device != DOCK:
            raise ValueError(f"{device} has no settings")
        doc: dict[str, Any] = {"version": self.settings.version, **self.settings.document()}
        doc["led"] = {**doc["led"], "dark": self.dark()}
        pending = self.pending()
        if pending is not None:
            doc["recalibrate"] = pending
        return doc

    def dark(self) -> bool:
        """Whether the light stays dark until the next reading: when the next
        slot falls outside the light's schedule."""
        slot = self._next_slot()
        if self.settings.led_schedule is None or slot is None:
            return False
        return not in_window(slot.time(), *self.settings.led_schedule)

    def _next_slot(self) -> datetime | None:
        now = self.now()
        wait = self.sync.seconds_until_next(now)
        return None if wait is None else datetime.fromtimestamp(now + wait, self.sync.tz)

    def _entry(self) -> dict:
        return self.reported(DOCK) or {}

    def _dock(self) -> dict:
        """The dock block of the dock's newest report."""
        client = (self._entry().get("doc") or {}).get("client") or {}
        dock = client.get("dock") if isinstance(client, dict) else None
        return dock if isinstance(dock, dict) else {}

    def offline(self) -> tuple[bool, int | None]:
        """Whether the dock has missed two of its slots, and how long ago it
        last reported. Not offline before its first report."""
        entry = self._entry()
        return bool(entry.get("offline")), entry.get("age_s")

    def last_recalibration(self) -> dict | None:
        """The dock's report of its last recalibration, or None."""
        done = self._dock().get("recalibrated")
        return done if isinstance(done, dict) and done.get("id") else None

    def pending(self) -> dict | None:
        """The recalibration the dock has yet to run, as ``{id, ppm}``."""
        done = self.last_recalibration() or {}
        done_id = done.get("id") if isinstance(done.get("id"), int) else 0
        return self.requests.pending(DOCK, done_id, self.now() - RECALIBRATE_WITHIN_S)

    def expired(self) -> dict | None:
        """The newest recalibration the dock never ran before it lapsed, as
        ``{id, ppm}``, or None."""
        done = self.last_recalibration() or {}
        done_id = done.get("id") if isinstance(done.get("id"), int) else 0
        newest = self.requests.pending(DOCK, done_id, 0)
        if newest is None or newest["id"] > self.now() - RECALIBRATE_WITHIN_S:
            return None
        return newest

    def next_sync(self) -> str:
        """The local time of the dock's next slot, as HH:MM; empty when it has none."""
        slot = self._next_slot()
        return slot.strftime("%H:%M") if slot else ""

    def recalibrate(self, ppm) -> int:
        """Ask the dock to recalibrate its SCD41 to ``ppm`` at its next
        reading. Returns the request's id.

        Raises:
            ValueError: ``ppm`` is out of range.
        """
        return self.requests.request(DOCK, "scd41", check_ppm(ppm), int(self.now()))

    def applied(self) -> tuple[bool | None, list[str]]:
        """Whether the dock runs these settings, None when it has not said,
        and the keys it refused."""
        reported = self._dock().get("settings")
        if not isinstance(reported, dict):
            return None, []
        refused = reported.get("refused")
        refused = [str(k) for k in refused] if isinstance(refused, list) else []
        return reported.get("version") == self.settings.version, refused
