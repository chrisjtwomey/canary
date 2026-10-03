"""Derived values and wording for the pages.

Pure functions over readings documents (docs/readings.md), so they are
tested without a browser.
"""
from __future__ import annotations

import functools
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo

from markupsafe import Markup


# The Magnus formula's constants, as the mock uses them for the reverse.
MAGNUS_A, MAGNUS_B = 17.62, 243.12


def dew_point_c(temp_c: float, rh_pct: float) -> float:
    """Magnus formula with the constants the mock uses for the reverse."""
    a, b = MAGNUS_A, MAGNUS_B
    rh = max(0.1, min(100.0, rh_pct))
    g = a * temp_c / (b + temp_c) + math.log(rh / 100.0)
    return b * g / (a - g)


# Upper limits in ppm. The bands follow the German UBA guidance: below
# 1000 is hygienically fine, 1000 to 2000 is elevated, above 2000 is not
# acceptable. The split below 1000 is ours.
CO2_BANDS = (
    (700, "Fresh air."),
    (1000, "Fresh enough."),
    (1500, "Getting stuffy."),
    (2000, "Stuffy. Open a window."),
)


def co2_verdict(ppm: float) -> str:
    for limit, words in CO2_BANDS:
        if ppm < limit:
            return words
    return "Stale. Air the room."


@dataclass(frozen=True)
class Comfort:
    """The comfort chart's edges, from config.yaml's comfort block, as
    (from, to) in C and in %: the comfortable ranges inside the acceptable
    ones. Each measurement has five bands: inside the comfortable range,
    between the two ranges on either side, and beyond the acceptable range
    on either side. A temperature edge is its setting at 50 % and leans with
    humidity; a humid edge is its setting at the comfortable range's middle
    temperature and follows a dew point; a dry edge is level. A value is
    judged as the pages show it, to 0.1 C and to 1 %, so a number never sits
    beside the word of the band next to it: 60.3 % shows as 60 %, inside
    an edge at 60."""
    temp: tuple[float, float] = (19.0, 24.0)
    rh: tuple[float, float] = (35.0, 60.0)
    acceptable_temp: tuple[float, float] = (17.0, 26.0)
    acceptable_rh: tuple[float, float] = (30.0, 65.0)

    @property
    def centre_c(self) -> float:
        """The comfortable range's middle temperature, where each humid edge
        is the % that its setting says."""
        return (self.temp[0] + self.temp[1]) / 2

    def humid_above(self, t: float) -> tuple[float, float]:
        """The humid edges at ``t``: the comfortable one and the acceptable
        one. Each follows a dew point, so it falls as the air warms."""
        return (rh_along_dew_point(self.rh[1], self.centre_c, t),
                rh_along_dew_point(self.acceptable_rh[1], self.centre_c, t))

    def temp_edges(self, rh: float) -> tuple[tuple[float, float], tuple[float, float]]:
        """The temperature edges at ``rh``: the comfortable (from, to) and the
        acceptable (from, to). Humid air feels a little warmer, so each edge
        is lower where the air is more humid."""
        return (tuple(temp_along_feel(e, rh) for e in self.temp),
                tuple(temp_along_feel(e, rh) for e in self.acceptable_temp))

    def temp_band(self, t: float, rh: float | None = None) -> str:
        """The temperature band; at 50 % without ``rh``."""
        shown = float(f"{t:.1f}")
        if rh is None:
            return _band(shown, self.temp, self.acceptable_temp, TEMP_BANDS)
        inner, outer = self.temp_edges(float(f"{rh:.0f}"))
        return _band(shown, inner, outer, TEMP_BANDS)

    def rh_band(self, rh: float, t: float | None = None) -> str:
        """The humidity band; at the centre temperature without ``t``."""
        shown = float(f"{rh:.0f}")
        if t is None:
            return _band(shown, self.rh, self.acceptable_rh, RH_BANDS)
        inner, outer = self.humid_above(float(f"{t:.1f}"))
        return _band(shown, (self.rh[0], inner), (self.acceptable_rh[0], outer), RH_BANDS)


def rh_along_dew_point(rh_at: float, at_c: float, t: float) -> float:
    """The relative humidity at ``t`` of the air that holds ``rh_at`` % at
    ``at_c``: the same water, so the same dew point. ASHRAE 55 sets its
    humidity limit this way, as water in the air, not as a percentage."""
    return rh_at * math.exp(MAGNUS_A * at_c / (MAGNUS_B + at_c) - MAGNUS_A * t / (MAGNUS_B + t))


# The person the temperature edges are for: sitting at a desk (1.1 met), in
# trousers, a long-sleeved shirt and a jumper (1.0 clo), in still air.
SITTING_MET, JUMPER_CLO, STILL_AIR_M_S = 1.1, 1.0, 0.1
# The humidity at which a temperature edge is its setting.
FEEL_RH = 50.0


def pmv(ta: float, rh: float, met: float = SITTING_MET, clo: float = JUMPER_CLO) -> float:
    """ISO 7730's predicted mean vote: how warm a person feels, from -3 cold
    to +3 hot, in air at ``ta`` C and ``rh`` %, with walls at the air's
    temperature."""
    pa = rh * 10 * math.exp(16.6536 - 4030.183 / (ta + 235))
    icl = 0.155 * clo
    m = met * 58.15
    fcl = 1 + 1.29 * icl if icl <= 0.078 else 1.05 + 0.645 * icl
    hcf = 12.1 * math.sqrt(STILL_AIR_M_S)
    taa = ta + 273
    tcla = taa + (35.5 - ta) / (3.5 * icl + 0.1)
    p1 = icl * fcl
    p2, p3, p4 = p1 * 3.96, p1 * 100, p1 * taa
    p5 = 308.7 - 0.028 * m + p2 * (taa / 100) ** 4
    # The clothing's surface temperature, by the standard's iteration.
    xn, xf = tcla / 100, tcla / 50
    hc = hcf
    for _ in range(150):
        if abs(xn - xf) <= 0.00015:
            break
        xf = (xf + xn) / 2
        hc = max(hcf, 2.38 * abs(100 * xf - taa) ** 0.25)
        xn = (p5 + p4 * hc - p2 * xf ** 4) / (100 + p3 * hc)
    tcl = 100 * xn - 273
    loss = (3.05e-3 * (5733 - 6.99 * m - pa)
            + (0.42 * (m - 58.15) if m > 58.15 else 0)
            + 1.7e-5 * m * (5867 - pa)
            + 0.0014 * m * (34 - ta)
            + 3.96 * fcl * (xn ** 4 - (taa / 100) ** 4)
            + fcl * hc * (tcl - ta))
    return (0.303 * math.exp(-0.036 * m) + 0.028) * (m - loss)


@functools.lru_cache(maxsize=4096)
def temp_along_feel(temp_at: float, rh: float) -> float:
    """The temperature at ``rh`` % that feels as ``temp_at`` does at 50 %:
    the same PMV, to 0.01 C. The pages judge a temperature against it."""
    if rh == FEEL_RH:
        return temp_at
    target = pmv(temp_at, FEEL_RH)
    lo, hi = temp_at - 15, temp_at + 15
    for _ in range(40):
        mid = (lo + hi) / 2
        if pmv(mid, rh) < target:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 2)


# Each measurement's bands, low to high.
TEMP_BANDS = ("cold", "cool", "comfortable", "warm", "hot")
RH_BANDS = ("very dry", "dry", "comfortable", "humid", "very humid")


def _band(v: float, inner: tuple[float, float], outer: tuple[float, float],
          names: tuple[str, ...]) -> str:
    if v < outer[0]:
        return names[0]
    if v < inner[0]:
        return names[1]
    if v > outer[1]:
        return names[4]
    if v > inner[1]:
        return names[3]
    return names[2]


COMFORT = Comfort()

# What the Comfort page says, by temperature band (rows) and humidity band
# (columns, as RH_BANDS orders them). The Settings page's live text reads
# this table too.
VERDICTS = {
    "cold": ("Cold and very dry.", "Cold and dry.", "Cold.", "Cold and damp.", "Dank."),
    "cool": ("Cool and very dry.", "Cool and dry.", "Cool.", "Cool and damp.", "Cool and damp."),
    "comfortable": ("Very dry.", "Dry.", "Comfortable.", "Muggy.", "Very humid."),
    "warm": ("Warm and very dry.", "Warm and dry.", "Warm.", "Warm and humid.",
             "Warm and very humid."),
    "hot": ("Hot and very dry.", "Hot and dry.", "Hot.", "Hot and humid.", "Sweltering."),
}


def comfort_verdict(temp_c: float, rh_pct: float, comfort: Comfort = COMFORT) -> str:
    return VERDICTS[comfort.temp_band(temp_c, rh_pct)][RH_BANDS.index(comfort.rh_band(rh_pct, temp_c))]


def thin(history: list[dict], step_s: int) -> list[dict]:
    """Every document that starts a new ``step_s`` interval, oldest first."""
    out: list[dict] = []
    last = None
    for doc in history:
        ts = doc["ts"]
        if last is not None and ts - last < step_s:
            continue
        out.append(doc)
        last = ts
    return out


def series(history: list[dict], key: str, step_s: int = 60) -> list[list]:
    """``[ts, value]`` pairs for ``key``. Documents without the key are skipped."""
    return [[d["ts"], d[key]] for d in thin([d for d in history if d.get(key) is not None], step_s)]


# The dock reads every 5 minutes by day and every 30 at night. Points further
# apart than this have a stretch with no reading between them.
GAP_S = 2700


def gaps(points: list[list], start: int, end: int, step_s: int = 0) -> list[list[int]]:
    """``[from, to]`` for each stretch of ``start``–``end`` with no point in it
    for longer than GAP_S, or than two ``step_s`` where the points were thinned
    to that step. A chart shades these and breaks its line across them."""
    limit = max(GAP_S, 2 * step_s)
    edges = [start] + [p[0] for p in points] + [end]
    return [[a, b] for a, b in zip(edges, edges[1:]) if b - a > limit]


def extremes(history: list[dict], key: str) -> tuple[dict | None, dict | None]:
    """The documents holding the lowest and the highest ``key``."""
    docs = [d for d in history if d.get(key) is not None]
    if not docs:
        return None, None
    return min(docs, key=lambda d: d[key]), max(docs, key=lambda d: d[key])


def y_range(values, floor=None, ceil=None, pad=0.0) -> dict:
    lo = min(values) - pad if values else 0.0
    hi = max(values) + pad if values else 1.0
    if floor is not None:
        lo = floor
    if ceil is not None:
        hi = max(ceil, hi)
    if hi <= lo:
        hi = lo + 1.0
    return {"min": lo, "max": hi}


def fmt_int(n: float) -> str:
    return f"{int(round(n)):,}"


def fmt_hm(ts: int, tz: tzinfo) -> str:
    return datetime.fromtimestamp(ts, tz).strftime("%H:%M")


def fmt_stamp(ts: int, tz: tzinfo) -> str:
    dt = datetime.fromtimestamp(ts, tz)
    return f"{dt.strftime('%a')} {dt.day} {dt.strftime('%b')}, {dt.strftime('%H:%M')}"


def hour_ticks(start: int, end: int, tz: tzinfo, every: int = 6) -> list[dict]:
    """Whole local hours divisible by ``every`` inside the window."""
    t = datetime.fromtimestamp(start, tz).replace(minute=0, second=0, microsecond=0)
    out = []
    while t.timestamp() <= end:
        ts = int(t.timestamp())
        if ts >= start and t.hour % every == 0:
            out.append({"x": ts, "label": t.strftime("%H")})
        t += timedelta(hours=1)
    return out


def night_spans(start: int, end: int, tz: tzinfo, dusk: int = 22, dawn: int = 7) -> list[list[int]]:
    """``[from, to]`` epoch spans of local night inside the window."""
    day = datetime.fromtimestamp(start, tz).replace(hour=0, minute=0, second=0, microsecond=0)
    day -= timedelta(days=1)
    stop = datetime.fromtimestamp(end, tz)
    out = []
    while day <= stop:
        a = day.replace(hour=dusk).timestamp()
        b = (day + timedelta(days=1)).replace(hour=dawn).timestamp()
        lo, hi = max(a, start), min(b, end)
        if lo < hi:
            out.append([int(lo), int(hi)])
        day += timedelta(days=1)
    return out


# ── Particulates ──────────────────────────────────────────────────────────

# WHO 2021 guideline for PM2.5 over 24 hours, 15 µg/m³, then its interim
# targets at 25, 37.5, 50 and 75.
PM25_BANDS = (
    (15, "Clean air."),
    (25, "Fine."),
    (37.5, "Some dust."),
    (50, "Dusty."),
    (75, "Bad air."),
)


def pm25_verdict(ug_m3: float) -> str:
    for limit, words in PM25_BANDS:
        if ug_m3 <= limit:
            return words
    return "Very bad air."


# ── VOCs ──────────────────────────────────────────────────────────────────

# Bosch's IAQ index bands.
IAQ_ZONES = (
    (0, 50, "excellent"),
    (50, 100, "good"),
    (100, 150, "light"),
    (150, 200, "moderate"),
    (200, 250, "heavy"),
    (250, 350, "severe"),
    (350, 500, "extreme"),
)
IAQ_WORDS = {
    "excellent": "Excellent air.",
    "good": "Good air.",
    "light": "A little stale.",
    "moderate": "Polluted.",
    "heavy": "Heavily polluted.",
    "severe": "Severely polluted.",
    "extreme": "Extremely polluted.",
}
IAQ_ACCURACY = ("calibrating", "low", "medium", "high")
# Bosch rates the index at its best only at accuracy 3 (BME688 datasheet,
# Table 3). Below it a page tags the index, or says it is calibrating where
# sources.corrections held the index back.
IAQ_CALIBRATED_ACCURACY = 3
CALIBRATING_TAG = "calibrating"
CALIBRATING_VERDICT = "Calibrating."


def iaq_zone(iaq: float) -> str:
    for lo, hi, name in IAQ_ZONES:
        if iaq < hi:
            return name
    return IAQ_ZONES[-1][2]


def iaq_verdict(iaq: float) -> str:
    return IAQ_WORDS[iaq_zone(iaq)]


# ── Humidity ──────────────────────────────────────────────────────────────

def abs_humidity_g_m3(temp_c: float, rh_pct: float) -> float:
    """Water vapour per cubic metre, the inverse of the mock's rh_from_abs."""
    es = 6.112 * math.exp(17.62 * temp_c / (243.12 + temp_c))
    return 216.7 * (rh_pct / 100.0 * es) / (temp_c + 273.15)


# ── Pressure ──────────────────────────────────────────────────────────────

def value_at(history: list[dict], key: str, ts: int, slack_s: int = 600):
    """The value of ``key`` in the newest document at or before ``ts``,
    if one lies within ``slack_s`` of it."""
    best = None
    for d in history:
        if d["ts"] <= ts and d.get(key) is not None and ts - d["ts"] <= slack_s:
            if best is None or d["ts"] > best["ts"]:
                best = d
    return None if best is None else best[key]


def pressure_tendency(history: list[dict], latest: dict, hours: int = 3):
    """Change in hPa over the last ``hours``, or None without both ends."""
    now = latest.get("pressure_hpa")
    then = value_at(history, "pressure_hpa", latest["ts"] - hours * 3600)
    if now is None or then is None:
        return None
    return now - then


# WMO calls a three-hour change under 1.6 hPa slight, and over 3.5 hPa rapid.
def tendency_words(delta) -> str:
    if delta is None:
        return "No trend yet."
    if delta >= 3.5:
        return "Rising fast."
    if delta >= 1.6:
        return "Rising."
    if delta <= -3.5:
        return "Falling fast."
    if delta <= -1.6:
        return "Falling."
    return "Steady."


# The legends printed on an aneroid barometer's dial.
BAROMETER_LEGENDS = (
    (980, "Stormy"),
    (1000, "Rain"),
    (1015, "Change"),
    (1030, "Fair"),
    (10000, "Very dry"),
)


def barometer_word(hpa: float) -> str:
    for limit, word in BAROMETER_LEGENDS:
        if hpa < limit:
            return word
    return BAROMETER_LEGENDS[-1][1]


# ── CO2 over the day ──────────────────────────────────────────────────────

def local_midnight(ts: int, tz: tzinfo) -> int:
    return int(datetime.fromtimestamp(ts, tz).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def minutes_above(history: list[dict], key: str, threshold: float, since: int) -> int:
    """Minutes with ``key`` above ``threshold`` from ``since`` on, counting one
    per document of the per-minute history."""
    return sum(1 for d in history if d["ts"] >= since and d.get(key) is not None and d[key] > threshold)


def ventilation_events(history: list[dict], key: str = "co2_ppm", drop: float = 100.0,
                       window_s: int = 900, gap_s: int = 2700) -> list[int]:
    """Times the room was aired: ``key`` fell by ``drop`` within ``window_s``.
    The time reported is where the fall is steepest over five minutes, which
    is when the window opened. One event per ``gap_s``, since a window stays
    open a while."""
    pts = series(history, key, 60)
    events: list[int] = []
    j = 0
    last = None
    for i, (t, v) in enumerate(pts):
        while j < len(pts) and pts[j][0] < t + window_s:
            j += 1
        if j >= len(pts):
            break
        if v - pts[j][1] < drop or (last is not None and t - last < gap_s):
            continue
        span = 5
        steepest = max(range(i, max(i + 1, j - span)),
                       key=lambda k: pts[k][1] - pts[min(k + span, len(pts) - 1)][1])
        events.append(pts[steepest][0])
        last = t
    return events


# ── The board ─────────────────────────────────────────────────────────────

NO_SENSOR_TAG = "no sensor"
NO_SENSOR_VERDICT = "No sensor."


def sensor_absent(status: dict | None, sensor: str) -> bool:
    """True when the newest report with a ``client.dock.sensors`` block says
    ``sensor`` is not running.

    Only the dock sends that block, and the display's reports are often newer,
    so the newest report of any board will not do. No such report, or one
    that does not name the sensor, counts as present, so a page keeps saying
    it is warming up until the board says otherwise.
    """
    status = status or {}
    boards = status.get("boards") or {}
    docs = [entry.get("doc") or {} for entry in boards.values()] or [status.get("doc") or {}]
    def sensors(doc: dict):
        return ((doc.get("client") or {}).get("dock") or {}).get("sensors")

    named = [d for d in docs if isinstance(sensors(d), dict)]
    if not named:
        return False
    return sensors(max(named, key=lambda d: d.get("ts") or 0)).get(sensor) is False


def rssi_quality(dbm: int) -> tuple[int, str]:
    """Bars out of four, and a word, for a WiFi signal."""
    if dbm >= -55:
        return 4, "strong"
    if dbm >= -65:
        return 3, "good"
    if dbm >= -75:
        return 2, "fair"
    if dbm >= -85:
        return 1, "weak"
    return 0, "none"


def fmt_duration(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s} s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} min"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h} h {m} min" if m else f"{h} h"
    d, h = divmod(h, 24)
    return f"{d} d {h} h" if h else f"{d} d"


def age_span(seconds: float) -> Markup:
    """fmt_duration's words in a span that ago.js counts on from there."""
    return Markup('<span data-age="{}">{}</span>').format(int(seconds), fmt_duration(seconds))


def in_span(seconds: float) -> Markup:
    """fmt_duration's words in a span that ago.js counts down from there, to "now"."""
    s = max(0, int(seconds))
    return Markup('<span data-in="{}">{}</span>').format(s, fmt_duration(s) if s else "now")


def fmt_bytes(n: float) -> str:
    if n >= 1024 * 1024:
        return f"{n / 1048576:.1f} MB"
    return f"{n / 1024:.0f} KB"


# ── Change over a window, and what it could mean ──────────────────────────

RATES = ("rising fast", "rising", "steady", "falling", "falling fast")


def change_over(history: list[dict], latest: dict, key: str, hours: float):
    """Change in ``key`` over the last ``hours``, or None without both ends."""
    now = latest.get(key)
    then = value_at(history, key, int(latest["ts"] - hours * 3600))
    if now is None or then is None:
        return None
    return now - then


def classify_rate(delta, slow: float, fast: float) -> str | None:
    """One of RATES: ``slow`` is the change that counts as moving,
    ``fast`` the change that counts as fast."""
    if delta is None:
        return None
    if delta >= fast:
        return "rising fast"
    if delta >= slow:
        return "rising"
    if delta <= -fast:
        return "falling fast"
    if delta <= -slow:
        return "falling"
    return "steady"


def rate_words(rate: str | None) -> str:
    if rate is None:
        return "No trend yet."
    return rate[0].upper() + rate[1:] + "."


# The meanings are what such a change usually means in a home. They are
# wording, not forecasts.

def pressure_meaning(rate: str, hpa: float) -> str:
    return {
        "rising fast": "Clearing quickly, with wind likely.",
        "rising": "Improving. Fair weather is likely.",
        "falling": "Rain or wind on the way, within a day.",
        "falling fast": "A storm is coming. Wind within hours.",
    }.get(rate) or (
        "Settled. More of the same." if hpa >= 1015
        else "Unsettled, and staying so." if hpa < 1000
        else "No change coming yet."
    )


def co2_meaning(rate: str, ppm: float) -> str:
    return {
        "rising fast": "People in the room and no air moving. Stuffy within the hour.",
        "rising": "Filling slowly. Ten minutes with a window open resets it.",
        "falling": "Clearing. A window is open, or the room has emptied.",
        "falling fast": "Aired. Fresh again in minutes.",
    }.get(rate) or (
        "Stale and staying stale. Air the room." if ppm >= 1000
        else "Holding. Fine for now." if ppm >= 700
        else "Fresh and staying fresh."
    )


def temp_meaning(rate: str, t: float, comfort: Comfort = COMFORT) -> str:
    return {
        "rising fast": "Warming quickly. Sun on the room, or the heating just came on.",
        "rising": "Warming up.",
        "falling": "Cooling. The heating is off.",
        "falling fast": "Cooling fast. A window or a door is open.",
    }.get(rate) or (
        "Holding comfortably." if (band := comfort.temp_band(t)) == "comfortable"
        else f"{band.capitalize()} and staying {band}."
    )


def rh_meaning(rate: str, rh: float, comfort: Comfort = COMFORT) -> str:
    return {
        "rising fast": "Steam. Cooking, a shower, or clothes drying.",
        "rising": "Getting damper. Moisture builds faster than it leaves.",
        "falling": "Drying out.",
        "falling fast": "Drying quickly. A window is open, or the heating is on.",
    }.get(rate) or {
        "very humid": "Very damp and staying so. Watch for condensation and mould.",
        "humid": "Damp and staying damp. Watch the windows for condensation.",
        "dry": "Dry. Skin and throats notice this.",
        "very dry": "Very dry. Eyes, skin and throats notice this.",
    }.get(comfort.rh_band(rh), "Holding comfortably.")


def pm_meaning(rate: str, ug: float) -> str:
    return {
        "rising fast": "Something is frying or burning. Open a window, and the extractor.",
        "rising": "Dust building. Cooking, candles, or a door to outside.",
        "falling": "Settling.",
        "falling fast": "Clearing fast. The air is moving.",
    }.get(rate) or (
        "Hanging in the air. Ventilate." if ug > 15
        else "Clean and staying clean."
    )


def iaq_meaning(rate: str, iaq: float) -> str:
    return {
        "rising fast": "Something new in the air. Cleaning, paint, cooking, or perfume.",
        "rising": "Building slowly. People, or something drying.",
        "falling": "Clearing.",
        "falling fast": "Clearing fast. A window is open.",
    }.get(rate) or (
        "Stale and staying stale. Air the room." if iaq >= 150
        else "A little stale, and staying so." if iaq >= 100
        else "Clean and staying clean."
    )


def temp_words(t: float, comfort: Comfort = COMFORT) -> str:
    return comfort.temp_band(t).capitalize() + "."


def rh_words(rh: float, comfort: Comfort = COMFORT) -> str:
    return comfort.rh_band(rh).capitalize() + "."


# ── Altitude ──────────────────────────────────────────────────────────────

def sea_level_hpa(hpa: float, altitude_m: float) -> float:
    """Station pressure reduced to sea level with the standard atmosphere,
    which is what forecasts and weather reports quote."""
    if not altitude_m:
        return hpa
    return hpa * (1 - 0.0065 * altitude_m / (288.15 + 0.0065 * altitude_m)) ** -5.257
