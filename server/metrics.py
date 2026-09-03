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
