"""Candidates for the pressure page, rendered side by side to choose from.
Whichever wins moves into pages/; the rest go."""
from __future__ import annotations

from datetime import datetime, timedelta

from airium import Airium

from metrics import (barometer_word, fmt_stamp, pressure_tendency, series, tendency_words,
                     value_at)
from pages.base import EnvPage
from pages.comfort import ComfortPage
from pages.day import ROWS, DayPage

TREND_HOURS = 3
ZONES = [
    {"from": 0, "to": 980, "label": "stormy", "gap": 5},
    {"from": 980, "to": 1000, "label": "rain", "gap": 8},
    {"from": 1000, "to": 1015, "label": "change", "gap": 12},
    {"from": 1015, "to": 1030, "label": "fair", "gap": 18},
    {"from": 1030, "to": 2000, "label": "very dry", "gap": 26},
]


def _stats(a: Airium, latest: dict, delta, valid: bool) -> None:
    hpa = latest.get("pressure_hpa")
    with a.div(klass="hero" + ("" if valid else " cold"), id="pressure"):
        a.span(klass="value", _t=f"{hpa:.1f}" if hpa is not None else "\u2014")
        a.span(klass="unit", _t="hPa")
    a.div(klass="verdict", _t=tendency_words(delta) if valid else "Warming up.")
    if valid and delta is not None:
        direction = "Up" if delta > 0 else "Down"
        a.div(klass="detail", _t=f"{direction} {abs(delta):.1f} hPa in {TREND_HOURS} hours. {barometer_word(hpa)}.")


class BarographPage(EnvPage):
    """Three days of pressure as a barograph trace."""
    title = "Barometer"
    stylesheet = "candidates/barograph.css"
    css_class = "barograph"
    requires = ("latest", "history_72h")
    DAYS = 3

    def body(self, a, latest, history_72h):
        valid = bool(latest.get("valid", {}).get("pressure")) and latest.get("pressure_hpa") is not None
        delta = pressure_tendency(history_72h, latest, TREND_HOURS) if valid else None
        a.div(klass="title label", _t="Barometer")
        a.div(klass="stamp", _t=fmt_stamp(latest["ts"], self.tz))
        with a.div(klass="stats"):
            _stats(a, latest, delta, valid)
        with a.div(klass="chart"):
            a.canvas(id="barograph")

    def charts(self, latest, history_72h):
        end = latest["ts"]
        start = end - self.DAYS * 86400
        pts = [p for p in series(history_72h, "pressure_hpa", 900) if p[0] >= start]
        recent = [p for p in series(history_72h, "pressure_hpa", 300) if p[0] >= end - TREND_HOURS * 3600]
        hpa = latest.get("pressure_hpa")
        if hpa is not None:
            pts.append([end, hpa])
            recent.append([end, hpa])
        values = [v for _, v in pts]
        lo, hi = (min(values), max(values)) if values else (1000, 1020)
        mid = (lo + hi) / 2
        span = max(hi - lo + 6, 20)
        y = {"min": round(mid - span / 2), "max": round(mid + span / 2)}
        yticks = [v for v in range(y["min"], y["max"] + 1) if v % 5 == 0]
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
        then = value_at(history_72h, "pressure_hpa", end - TREND_HOURS * 3600)
        return [{
            "kind": "barograph", "canvas": "#barograph",
            "points": pts, "recent": recent,
            "x": {"min": start, "max": end}, "y": y, "yticks": yticks,
            "zones": ZONES, "days": days, "dayLabels": labels,
            "set": [end - TREND_HOURS * 3600, then] if then is not None else None,
            "now": [end, hpa] if hpa is not None else None,
        }]


def tendency_shape(history, latest, hours=TREND_HOURS):
    """The WMO characteristic: what each half of the window did."""
    now = latest.get("pressure_hpa")
    mid = value_at(history, "pressure_hpa", latest["ts"] - hours * 1800)
    then = value_at(history, "pressure_hpa", latest["ts"] - hours * 3600)
    if now is None or mid is None or then is None:
        return None

    def cls(d):
        return "rising" if d >= 0.4 else "falling" if d <= -0.4 else "steady"
    return cls(mid - then), cls(now - mid)


SHAPE_WORDS = {
    ("rising", "rising"): "Rising steadily.", ("rising", "steady"): "Rising, then steady.",
    ("rising", "falling"): "Rising, then falling.", ("steady", "rising"): "Steady, then rising.",
    ("steady", "steady"): "Steady.", ("steady", "falling"): "Steady, then falling.",
    ("falling", "rising"): "Falling, then rising.", ("falling", "steady"): "Falling, then steady.",
    ("falling", "falling"): "Falling steadily.",
}


class TendencyPage(EnvPage):
    """The three-hour change as the hero, the WMO symbol as the picture."""
    title = "Barometer"
    stylesheet = "candidates/tendency.css"
    css_class = "tendency"
    requires = ("latest", "history_24h")

    def body(self, a, latest, history_24h):
        hpa = latest.get("pressure_hpa")
        valid = bool(latest.get("valid", {}).get("pressure")) and hpa is not None
        delta = pressure_tendency(history_24h, latest, TREND_HOURS) if valid else None
        shape = tendency_shape(history_24h, latest) if valid else None
        a.div(klass="title label", _t="Barometer")
        a.div(klass="stamp", _t=fmt_stamp(latest["ts"], self.tz))
        with a.div(klass="symbol"):
            a.canvas(id="tendency")
        with a.div(klass="stats"):
            with a.div(klass="hero", id="delta"):
                a.span(klass="value", _t=f"{delta:+.1f}" if delta is not None else "\u2014")
                a.span(klass="unit", _t=f"hPa in {TREND_HOURS} h")
            a.div(klass="verdict", _t=SHAPE_WORDS[shape] if shape else "No trend yet.")
            if valid:
                a.div(klass="detail", _t=f"{hpa:.1f} hPa. {barometer_word(hpa)}.")

    def charts(self, latest, history_24h):
        shape = tendency_shape(history_24h, latest)
        if not shape:
            return []
        return [{"kind": "tendency", "canvas": "#tendency", "first": shape[0], "second": shape[1]}]


class ColumnPage(EnvPage):
    """A vertical scale zoomed to \u00b115 hPa, with marks for 3 and 24 hours ago."""
    title = "Barometer"
    stylesheet = "candidates/column.css"
    css_class = "column"
    requires = ("latest", "history_24h")

    def body(self, a, latest, history_24h):
        valid = bool(latest.get("valid", {}).get("pressure")) and latest.get("pressure_hpa") is not None
        delta = pressure_tendency(history_24h, latest, TREND_HOURS) if valid else None
        a.div(klass="title label", _t="Barometer")
        a.div(klass="stamp", _t=fmt_stamp(latest["ts"], self.tz))
        with a.div(klass="column"):
            a.canvas(id="column")
        with a.div(klass="stats"):
            _stats(a, latest, delta, valid)

    def charts(self, latest, history_24h):
        hpa = latest.get("pressure_hpa")
        if hpa is None:
            return []
        marks = []
        for hours, label in ((3, "3 h ago"), (24, "24 h ago")):
            v = value_at(history_24h, "pressure_hpa", latest["ts"] - hours * 3600)
            if v is not None:
                marks.append({"y": v, "label": label})
        return [{"kind": "column", "canvas": "#column", "min": round(hpa) - 15, "max": round(hpa) + 15,
                 "value": hpa, "zones": ZONES, "marks": marks}]


class DayPressurePage(DayPage):
    """Day with pressure as a fifth ribbon."""
    stylesheet = "candidates/day-five.css"
    css_class = "day five"
    rows = ROWS + (("pressure_hpa", "Pressure", "hPa", lambda v: f"{v:.1f}", {"pad": 2.0}),)


class ComfortPressurePage(ComfortPage):
    """Comfort with the pressure tendency in words."""

    def extra_detail(self, latest, history_24h):
        hpa = latest.get("pressure_hpa")
        if hpa is None:
            return None
        words = tendency_words(pressure_tendency(history_24h, latest, TREND_HOURS)).rstrip(".").lower()
        return f"Pressure {hpa:.1f} hPa, {words}."
