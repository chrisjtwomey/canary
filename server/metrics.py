"""Derived values and wording for the pages.

Pure functions over readings documents (docs/READINGS.md), so they are
tested without a browser.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, tzinfo


def dew_point_c(temp_c: float, rh_pct: float) -> float:
    """Magnus formula with the constants the mock uses for the reverse."""
    a, b = 17.62, 243.12
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


COMFORT_T = (19.0, 24.0)
COMFORT_RH = (35.0, 60.0)
ACCEPTABLE_T = (17.0, 26.0)
ACCEPTABLE_RH = (30.0, 65.0)


def comfort_verdict(temp_c: float, rh_pct: float) -> str:
    warm = temp_c > COMFORT_T[1]
    cool = temp_c < COMFORT_T[0]
    humid = rh_pct > COMFORT_RH[1]
    dry = rh_pct < COMFORT_RH[0]
    if not (warm or cool or humid or dry):
        return "Comfortable."
    first = "Warm" if warm else "Cool" if cool else ""
    second = "humid" if humid else "dry" if dry else ""
    if first and second:
        return f"{first} and {second}."
    return (first or second.capitalize()) + "."


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


def temp_meaning(rate: str, t: float) -> str:
    return {
        "rising fast": "Warming quickly. Sun on the room, or the heating just came on.",
        "rising": "Warming up.",
        "falling": "Cooling. The heating is off.",
        "falling fast": "Cooling fast. A window or a door is open.",
    }.get(rate) or (
        "Warm and staying warm." if t > COMFORT_T[1]
        else "Cool and staying cool." if t < COMFORT_T[0]
        else "Holding comfortably."
    )


def rh_meaning(rate: str, rh: float) -> str:
    return {
        "rising fast": "Steam. Cooking, a shower, or clothes drying.",
        "rising": "Getting damper. Moisture builds faster than it leaves.",
        "falling": "Drying out.",
        "falling fast": "Drying quickly. A window is open, or the heating is on.",
    }.get(rate) or (
        "Damp and staying damp. Watch the windows for condensation." if rh > COMFORT_RH[1]
        else "Dry. Skin and throats notice this." if rh < COMFORT_RH[0]
        else "Holding comfortably."
    )


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


def temp_words(t: float) -> str:
    if t > COMFORT_T[1]:
        return "Warm."
    if t < COMFORT_T[0]:
        return "Cool."
    return "Comfortable."


def rh_words(rh: float) -> str:
    if rh > COMFORT_RH[1]:
        return "Humid."
    if rh < COMFORT_RH[0]:
        return "Dry."
    return "Comfortable."


# ── Altitude ──────────────────────────────────────────────────────────────

def sea_level_hpa(hpa: float, altitude_m: float) -> float:
    """Station pressure reduced to sea level with the standard atmosphere,
    which is what forecasts and weather reports quote."""
    if not altitude_m:
        return hpa
    return hpa * (1 - 0.0065 * altitude_m / (288.15 + 0.0065 * altitude_m)) ** -5.257
