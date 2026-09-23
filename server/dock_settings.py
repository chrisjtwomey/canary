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
             "starting": {"pattern": "pulse", "interval_s": 0.5}, ...},
     "log": {"level": "debug"},
     "bsec": {"sample_s": 300},
     "recalibrate": {"id": 1758650400, "ppm": 420}}

The dock reports what it applied in its client status, as ``settings`` with
the version and any keys it refused, and its last recalibration as
``recalibrated``.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from epd_server.config import ConfigError, get_prop_by_keys

from schedule import PostSchedule

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
# The light's looks: each state the dock can be in, highest first, with its
# look by default. The dock shows the first that holds; its update has a look
# of its own that no setting changes.
LED_PATTERNS = ("off", "solid", "pulse", "flash")
LED_LOOKS = (("starting", "pulse", 0.5), ("no_wifi", "flash", 1),
             ("post_failed", "flash", 2), ("sensor_missing", "flash", 3),
             ("well", "pulse", 1))
LED_INTERVAL_MIN_S = 0.25
LED_INTERVAL_MAX_S = 10.0
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
    led_off_in_quiet_hours: bool = False
    log_level: str = "debug"
    bsec_sample_s: int = 300
    led_looks: tuple[tuple[str, str, float], ...] = LED_LOOKS   # (state, pattern, interval_s)

    def document(self) -> dict:
        """The settings as the dock reads them, without the version."""
        return {
            "pm": {"warmup_s": self.pm_warmup_s},
            "scd41": {"temperature_offset_c": self.scd41_temperature_offset_c,
                      "self_calibration": self.scd41_self_calibration},
            "shtc3": {"low_power": self.shtc3_low_power},
            "led": {"brightness_pct": self.led_brightness_pct,
                    **{state: {"pattern": pattern, "interval_s": interval}
                       for state, pattern, interval in self.led_looks}},
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


def _led_look(config: dict, state: str, pattern: str, interval: float) -> tuple[str, str, float]:
    chosen = _get(config, f"led.{state}.pattern", pattern)
    if chosen not in LED_PATTERNS:
        raise ConfigError(f"dock.led.{state}.pattern must be one of {', '.join(LED_PATTERNS)}, "
                          f"not {chosen!r}")
    every = _get(config, f"led.{state}.interval_s", interval)
    if isinstance(every, bool) or not isinstance(every, (int, float)) \
            or not LED_INTERVAL_MIN_S <= every <= LED_INTERVAL_MAX_S:
        raise ConfigError(f"dock.led.{state}.interval_s must be from {LED_INTERVAL_MIN_S:g} to "
                          f"{LED_INTERVAL_MAX_S:g}, not {every!r}")
    return state, chosen, round(float(every), 3)


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
        led_off_in_quiet_hours=_bool(config, "led.off_in_quiet_hours", False),
        log_level=level,
        bsec_sample_s=rate,
        led_looks=tuple(_led_look(config, *look) for look in LED_LOOKS),
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
        posts: the dock's post schedule, for the light's quiet hours.
        requests: where a recalibration waits; see CalibrationStore.
        reported: what the server knows of a device, as DeviceReports.device
            gives it, or None.
        now: the clock, for tests.
    """

    def __init__(self, settings: DockSettings, posts: PostSchedule, requests,
                 reported: Callable[[str], dict | None],
                 now: Callable[[], float] = time.time):
        self.settings = settings
        self.posts = posts
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
        slot falls in quiet hours and the settings ask for it."""
        if not self.settings.led_off_in_quiet_hours:
            return False
        now = self.now()
        slot = now + self.posts.seconds_until_next(now)
        return self.posts.quiet(datetime.fromtimestamp(slot, self.posts.tz))

    def _entry(self) -> dict:
        return self.reported(DOCK) or {}

    def _client(self) -> dict:
        client = (self._entry().get("doc") or {}).get("client")
        return client if isinstance(client, dict) else {}

    def offline(self) -> tuple[bool, int | None]:
        """Whether the dock has missed two of its slots, and how long ago it
        last reported. Not offline before its first report."""
        entry = self._entry()
        return bool(entry.get("offline")), entry.get("age_s")

    def last_recalibration(self) -> dict | None:
        """The dock's report of its last recalibration, or None."""
        done = self._client().get("recalibrated")
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

    def next_report(self) -> str:
        """The local time of the dock's next slot, as HH:MM."""
        now = self.now()
        slot = now + self.posts.seconds_until_next(now)
        return datetime.fromtimestamp(slot, self.posts.tz).strftime("%H:%M")

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
        reported = self._client().get("settings")
        if not isinstance(reported, dict):
            return None, []
        refused = reported.get("refused")
        refused = [str(k) for k in refused] if isinstance(refused, list) else []
        return reported.get("version") == self.settings.version, refused
