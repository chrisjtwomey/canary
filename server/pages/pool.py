"""A metric's pool of pages: the same two shapes for every measurement.

TracePage shows the value now with three days behind it and the
thresholds that matter. DeltaPage shows the change over a window, where
the value stood before, and what such a change usually means.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from airium import Airium

from metrics import (NO_SENSOR_TAG, NO_SENSOR_VERDICT, barometer_word, change_over, classify_rate,
                     co2_meaning, co2_verdict, extremes, fmt_hm, fmt_int, fmt_stamp, iaq_meaning,
                     iaq_verdict, pm25_verdict, pm_meaning, pressure_meaning, rate_words, rh_meaning,
                     rh_words, sensor_absent, series, temp_meaning, temp_words, value_at)
from pages.base import EnvPage


@dataclass(frozen=True)
class Metric:
    key: str
    title: str                       # the page's small-caps title
    unit: str
    fmt: Callable[[float], str]
    valid_flag: str
    window_h: float                  # the delta window
    slow: float                      # a change this big is rising or falling
    fast: float                      # a change this big is fast
    guides: tuple                    # ((value, label), ...): dashed lines on the trace
    span: float                      # the column shows ± this around now
    level_words: Callable[[float], str]
    meaning: Callable[[str, float], str]
    floor: float | None = None
    ceil: float | None = None
    pad: float = 0.0
    second: "Metric | None" = None   # drawn lighter beside this one on the trace
    cold_tag: str = "warming up"
    sensor: str = ""                 # its key in the board's client.sensors block


def _f1(v):
    return f"{v:.1f}"


def _f0(v):
    return f"{v:.0f}"


# The delta windows are short: a room changes in minutes. Pressure gets an
# hour, since it moves in hours. slow and fast are changes over that window.
RH = Metric("rh_pct", "Humidity", "%", _f0, "temp_humidity", 0.25, 3, 8,
            ((35, "dry"), (60, "humid")), 20, rh_words, rh_meaning, pad=5, sensor="shtc3")
TEMP = Metric("temp_c", "Temperature", "°C", _f1, "temp_humidity", 0.25, 0.3, 0.8,
              ((19, "cool"), (24, "warm")), 5, temp_words, temp_meaning, pad=1, second=RH,
              sensor="shtc3")
CO2 = Metric("co2_ppm", "Carbon dioxide", "ppm", fmt_int, "co2", 0.25, 40, 120,
             ((700, "fresh"), (1000, "stuffy")), 400, co2_verdict, co2_meaning,
             floor=400, ceil=1200, pad=50, sensor="scd41")
PM25 = Metric("pm2_5", "Fine dust", "µg/m³", fmt_int, "particulates", 0.25, 3, 15,
              ((15, "WHO guideline"),), 30, pm25_verdict, pm_meaning,
              floor=0, ceil=20, pad=5, cold_tag="fan warming up", sensor="pmsa003i")
IAQ = Metric("iaq", "Air quality", "IAQ", _f0, "gas", 0.25, 8, 25,
             ((50, "good"), (150, "stale")), 100, iaq_verdict, iaq_meaning,
             floor=0, ceil=200, pad=20, cold_tag="heater warming up", sensor="bme688")
PRESSURE = Metric("pressure_hpa", "Barometer", "hPa", _f1, "pressure", 1, 0.6, 1.2,
                  ((980, "rain"), (1000, "change"), (1015, "fair"), (1030, "very dry")), 15,
                  lambda v: barometer_word(v) + ".", pressure_meaning, pad=3, cold_tag="no reading",
                  sensor="bme688")


def _valid(latest: dict, m: Metric) -> bool:
    return bool(latest.get("valid", {}).get(m.valid_flag)) and latest.get(m.key) is not None


def _cold_words(m: Metric, absent: bool) -> tuple[str, str]:
    """The tag beside the dash, and the verdict, when there is no valid reading."""
    return (NO_SENSOR_TAG, NO_SENSOR_VERDICT) if absent else (m.cold_tag, "Warming up.")


def _hero(a: Airium, latest: dict, m: Metric, id: str, absent: bool) -> None:
    v = latest.get(m.key)
    ok = _valid(latest, m)
    with a.div(klass="hero" + ("" if ok else " cold"), id=id):
        a.span(klass="value", _t=m.fmt(v) if v is not None else "—")
        a.span(klass="unit", _t=m.unit)
        if not ok:
            a.span(klass="cold-tag", _t=_cold_words(m, absent)[0])


def _window_words(hours: float) -> str:
    return f"{int(hours)} h" if hours >= 1 else f"{int(hours * 60)} min"


class TracePage(EnvPage):
    """The value now, three days behind it, the thresholds as dashed lines."""
    stylesheet = "trace.css"
    css_class = "trace"
    requires = ("latest", "history_72h", "status")
    DAYS = 3

    def __init__(self, name: str, metric: Metric, **kwargs):
        super().__init__(name, **kwargs)
        self.metric = metric
        self.title = metric.title

    def body(self, a: Airium, **data) -> None:
        latest: dict = data["latest"]
        history_72h: list[dict] = data["history_72h"]
        m = self.metric
        ok = _valid(latest, m)
        absent = sensor_absent(data.get("status"), m.sensor)
        a.div(klass="title label", _t=m.title)
        a.div(klass="stamp", _t=fmt_stamp(latest["ts"], self.tz))
        with a.div(klass="stats"):
            _hero(a, latest, m, "now", absent)
            a.div(klass="verdict",
                  _t=m.level_words(latest[m.key]) if ok else _cold_words(m, absent)[1])
            lo, hi = extremes(history_72h + [latest], m.key)
            if lo and hi:
                a.div(klass="detail", _t=(
                    f"High of {m.fmt(hi[m.key])} {self._when(hi['ts'], latest['ts'])}, "
                    f"low of {m.fmt(lo[m.key])} {self._when(lo['ts'], latest['ts'])}."))
        with a.div(klass="chart"):
            a.canvas(id="trace")

    def _when(self, ts: int, now: int) -> str:
        day = datetime.fromtimestamp(ts, self.tz).date()
        today = datetime.fromtimestamp(now, self.tz).date()
        if day == today:
            return f"at {fmt_hm(ts, self.tz)}"
        if day == today - timedelta(days=1):
            return f"yesterday at {fmt_hm(ts, self.tz)}"
        return f"{datetime.fromtimestamp(ts, self.tz).strftime('%A')} at {fmt_hm(ts, self.tz)}"

    def _series(self, history: list[dict], key: str, start: int, latest: dict):
        pts = [p for p in series(history, key, 900) if p[0] >= start]
        if latest.get(key) is not None:
            pts.append([latest["ts"], latest[key]])
        return pts

    def _range(self, pts, m: Metric) -> dict:
        values = [v for _, v in pts]
        if not values:
            return {"min": m.floor or 0, "max": (m.ceil or 1)}
        lo, hi = min(values) - m.pad, max(values) + m.pad
        if m.floor is not None:
            lo = min(m.floor, lo)
        if m.ceil is not None:
            hi = max(m.ceil, hi)
        return {"min": lo, "max": hi}

    def charts(self, **data) -> list[dict]:
        latest: dict = data["latest"]
        history_72h: list[dict] = data["history_72h"]
        m = self.metric
        end = latest["ts"]
        start = end - self.DAYS * 86400
        pts = self._series(history_72h, m.key, start, latest)
        recent = [p for p in series(history_72h, m.key, 300) if p[0] >= end - m.window_h * 3600]
        if latest.get(m.key) is not None:
            recent.append([end, latest[m.key]])
        y = self._range(pts, m)
        span = y["max"] - y["min"]
        step = 1 if span <= 12 else 5 if span <= 30 else 10 if span <= 150 else 100 if span <= 1000 else 500
        yticks = [v for v in range(int(y["min"]) - 1, int(y["max"]) + 2) if v % step == 0 and y["min"] <= v <= y["max"]]
        day = datetime.fromtimestamp(start, self.tz).replace(hour=0, minute=0, second=0, microsecond=0)
        days, labels = [], []
        while day.timestamp() <= end:
            ts = int(day.timestamp())
            if ts > start:
                days.append({"x": ts})
            noon = int((day + timedelta(hours=12)).timestamp())
            if start < noon < end:
                labels.append({"x": noon, "label": day.strftime("%A")})
            day += timedelta(days=1)
        then = value_at(history_72h, m.key, end - int(m.window_h * 3600))
        spec = {
            "kind": "trace", "canvas": "#trace",
            "points": pts, "recent": recent,
            "x": {"min": start, "max": end}, "y": y, "yticks": yticks,
            "guides": [{"y": v, "label": label} for v, label in m.guides],
            "days": days, "dayLabels": labels,
            "set": [end - int(m.window_h * 3600), then] if then is not None else None,
            "now": [end, latest[m.key]] if latest.get(m.key) is not None else None,
        }
        if m.second is not None:
            pts2 = self._series(history_72h, m.second.key, start, latest)
            spec["points2"] = pts2
            spec["y2"] = self._range(pts2, m.second)
            spec["label2"] = f"{m.second.title.lower()}, {m.second.unit}"
        return [spec]


class DeltaPage(EnvPage):
    """The change over a window, where the value stood, and what it may mean."""
    stylesheet = "delta.css"
    css_class = "delta"
    requires = ("latest", "history_24h", "status")

    def __init__(self, name: str, metric: Metric, **kwargs):
        super().__init__(name, **kwargs)
        self.metric = metric
        self.title = metric.title

    def _block(self, a: Airium, latest: dict, history: list[dict], m: Metric, main: bool,
               absent: bool) -> None:
        ok = _valid(latest, m)
        delta = change_over(history, latest, m.key, m.window_h) if ok else None
        rate = classify_rate(delta, m.slow, m.fast)
        decimals = 1 if m.fmt is _f1 else 0
        shown = round(delta, decimals) + 0.0 if delta is not None else None   # no "-0"
        with a.div(klass="hero" + ("" if ok else " cold"), id=f"delta-{m.key}"):
            a.span(klass="value", _t=f"{shown:+.{decimals}f}" if shown is not None else "—")
            a.span(klass="unit", _t=f"{m.unit} in {_window_words(m.window_h)}")
            if not ok:
                a.span(klass="cold-tag", _t=_cold_words(m, absent)[0])
        a.div(klass="verdict", _t=rate_words(rate) if ok else _cold_words(m, absent)[1],
              id=f"rate-{m.key}")
        if ok:
            a.div(klass="detail", _t=f"{m.fmt(latest[m.key])} {m.unit} now. {m.level_words(latest[m.key])}")
            if rate is not None:
                a.div(klass="meaning", id=f"meaning-{m.key}", _t=m.meaning(rate, latest[m.key]))

    def body(self, a: Airium, **data) -> None:
        latest: dict = data["latest"]
        history_24h: list[dict] = data["history_24h"]
        m = self.metric
        status = data.get("status")
        a.div(klass="title label", _t=m.title)
        a.div(klass="stamp", _t=fmt_stamp(latest["ts"], self.tz))
        with a.div(klass="columns" + (" two" if m.second else "")):
            with a.div(klass="column"):
                a.canvas(id="column")
            if m.second is not None:
                with a.div(klass="column"):
                    a.canvas(id="column2")
        with a.div(klass="stats"):
            with a.div(klass="block main"):
                self._block(a, latest, history_24h, m, True, sensor_absent(status, m.sensor))
            if m.second is not None:
                with a.div(klass="block second"):
                    self._block(a, latest, history_24h, m.second, False,
                                sensor_absent(status, m.second.sensor))

    def _column(self, latest: dict, history: list[dict], m: Metric, canvas: str) -> dict:
        v = latest.get(m.key) if _valid(latest, m) else None
        centre = v if v is not None else (m.floor or 0) + m.span
        marks = []
        for hours in (m.window_h, 3):
            w = value_at(history, m.key, latest["ts"] - int(hours * 3600))
            if w is not None:
                marks.append({"y": w, "label": f"{_window_words(hours)} ago"})
        lo, hi = round(centre - m.span), round(centre + m.span)
        if m.floor is not None and lo < m.floor:
            lo, hi = m.floor, m.floor + 2 * m.span
        return {"kind": "column", "canvas": canvas, "min": lo, "max": hi, "value": v,
                "unit": m.unit, "guides": [{"y": g, "label": label} for g, label in m.guides],
                "marks": marks}

    def charts(self, **data) -> list[dict]:
        latest: dict = data["latest"]
        history_24h: list[dict] = data["history_24h"]
        m = self.metric
        specs = [self._column(latest, history_24h, m, "#column")]
        if m.second is not None:
            specs.append(self._column(latest, history_24h, m.second, "#column2"))
        return specs
