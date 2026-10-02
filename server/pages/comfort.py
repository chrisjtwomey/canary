"""Comfort: temperature and humidity as one point on the comfort chart."""
from __future__ import annotations

import math

from airium import Airium

from metrics import (COMFORT, NO_SENSOR_TAG, NO_SENSOR_VERDICT, Comfort, abs_humidity_g_m3,
                     comfort_verdict, dew_point_c, fmt_stamp, rh_along_dew_point, sensor_absent,
                     temp_along_feel, thin)
from pages.base import EnvPage

TRAIL_HOURS = 6
TRAIL_STEP_S = 600
# Where along its side of the comfortable area an edge's word may go.
PLACES = (0.2, 0.35, 0.5, 0.65, 0.8)


def _meet(c: Comfort, temp_at: float, rh_at: float) -> float:
    """The % where the temperature edge set at ``temp_at`` meets the humid
    edge set at ``rh_at``: the two cross once, as one leans and the other
    falls."""
    lo, hi = 0.0, 100.0
    if hi <= rh_along_dew_point(rh_at, c.centre_c, temp_along_feel(temp_at, hi)):
        return hi
    for _ in range(30):
        mid = (lo + hi) / 2
        if mid < rh_along_dew_point(rh_at, c.centre_c, temp_along_feel(temp_at, mid)):
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 2)


def _temp_line(temp_at: float, rh0: float, rh1: float) -> list[list[float]]:
    """A temperature edge from ``rh0`` up to ``rh1`` %, as [t, rh] in 5 % steps."""
    rhs = [rh0, *range(int(rh0 // 5 + 1) * 5, int(math.ceil(rh1)), 5), rh1]
    return [[temp_along_feel(temp_at, rh), rh] for rh in rhs]


def _humid_line(c: Comfort, rh_at: float, t0: float, t1: float) -> list[list[float]]:
    """A humid edge from ``t0`` to ``t1`` C, as [t, rh] in 0.5 C steps."""
    ts = [t0, *(i / 2 for i in range(int(t0 * 2) + 1, int(math.ceil(t1 * 2)))), t1]
    return [[t, round(rh_along_dew_point(rh_at, c.centre_c, t), 2)] for t in ts]


def comfort_lines(c: Comfort) -> list[dict]:
    """The four comfortable edges, each to where its acceptable edges are,
    with five places along the comfortable area's side for its word, each as
    [t, rh, t2, rh2]: the place, and a point further along, so the word
    follows the edge. ``out`` is the way from the area to the word's side.
    charts.js writes the word at the place farthest from the room's last
    hours."""
    (t0, t1), (a0, a1) = c.temp, c.acceptable_temp
    (dry, wet), (a_dry, a_wet) = c.rh, c.acceptable_rh
    top0, top1 = _meet(c, t0, wet), _meet(c, t1, wet)
    h0, h1 = temp_along_feel(t0, top0), temp_along_feel(t1, top1)
    def humid(t: float) -> float:
        return rh_along_dew_point(wet, c.centre_c, t)
    def up(temp_at: float) -> list[list[float]]:
        return [[temp_along_feel(temp_at, rh), rh, temp_along_feel(temp_at, rh + 1), rh + 1]
                for rh in (dry + f * (_meet(c, temp_at, wet) - dry) for f in PLACES)]
    def across(rh_of, t_from: float, t_to: float) -> list[list[float]]:
        return [[t, rh_of(t), t + 0.5, rh_of(t + 0.5)]
                for t in (t_from + f * (t_to - t_from) for f in PLACES)]
    def level(t: float) -> float:
        return dry
    cold_wet, hot_wet = _meet(c, a0, wet), _meet(c, a1, wet)
    return [
        {"text": "cool", "points": _temp_line(t0, a_dry, _meet(c, t0, a_wet)), "at": up(t0), "out": [-1, 0]},
        {"text": "warm", "points": _temp_line(t1, a_dry, _meet(c, t1, a_wet)), "at": up(t1), "out": [1, 0]},
        {"text": "humid", "points": _humid_line(c, wet, temp_along_feel(a0, cold_wet),
                                                temp_along_feel(a1, hot_wet)),
         "at": across(humid, h0, h1), "out": [0, 1]},
        {"text": "dry", "points": [[temp_along_feel(a0, dry), dry], [temp_along_feel(a1, dry), dry]],
         "at": across(level, temp_along_feel(t0, dry), temp_along_feel(t1, dry)), "out": [0, -1]},
    ]


def comfort_area(c: Comfort) -> list[list[float]]:
    """The comfortable area's outline, as [t, rh] corners: up the cool edge,
    along the humid edge, down the warm edge."""
    (t0, t1), (dry, wet) = c.temp, c.rh
    top0, top1 = _meet(c, t0, wet), _meet(c, t1, wet)
    return [*_temp_line(t0, dry, top0),
            *_humid_line(c, wet, temp_along_feel(t0, top0), temp_along_feel(t1, top1))[1:-1],
            *reversed(_temp_line(t1, dry, top1))]


class ComfortPage(EnvPage):
    title = "Comfort"
    stylesheet = "comfort.css"
    css_class = "comfort"
    requires = ("latest", "history_24h", "status")

    def __init__(self, name: str, comfort: Comfort = COMFORT, **kwargs):
        super().__init__(name, **kwargs)
        self.comfort = comfort

    def body(self, a: Airium, **data) -> None:
        latest: dict = data["latest"]
        history_24h: list[dict] = data["history_24h"]
        temp = latest.get("temp_c")
        rh = latest.get("rh_pct")
        valid = bool(latest.get("valid", {}).get("temp_humidity")) and temp is not None and rh is not None
        absent = sensor_absent(data.get("status"), "shtc3")

        a.div(klass="title label", _t="Comfort")
        a.div(klass="stamp", _t=fmt_stamp(latest["ts"], self.tz))

        with a.div(klass="chart"):
            a.canvas(id="comfort-chart")

        with a.div(klass="stats"):
            with a.div(klass="stat"):
                with a.div(klass="hero" + ("" if valid else " cold"), id="temp"):
                    a.span(klass="value", _t=f"{temp:.1f}" if temp is not None else "—")
                    a.span(klass="unit", _t="°C")
                    if not valid:
                        a.span(klass="cold-tag", _t=NO_SENSOR_TAG if absent else "warming up")
                a.div(klass="label", _t="Temperature")
            with a.div(klass="stat"):
                with a.div(klass="hero" + ("" if valid else " cold"), id="rh"):
                    a.span(klass="value", _t=f"{rh:.0f}" if rh is not None else "—")
                    a.span(klass="unit", _t="%")
                a.div(klass="label", _t="Humidity")
            verdict = NO_SENSOR_VERDICT if absent else "Warming up."
            if valid:
                assert temp is not None and rh is not None   # what valid means
                a.div(klass="detail", _t=(
                    f"Dew point {dew_point_c(temp, rh):.1f}°, "
                    f"vapour {abs_humidity_g_m3(temp, rh):.1f} g/m³."))
                verdict = comfort_verdict(temp, rh, self.comfort)
            extra = self.extra_detail(latest, history_24h)
            if extra:
                a.div(klass="detail", _t=extra)
            a.div(klass="verdict", _t=verdict)

    def extra_detail(self, latest: dict, history_24h: list[dict]) -> str | None:
        return None

    def charts(self, **data) -> list[dict]:
        latest: dict = data["latest"]
        history_24h: list[dict] = data["history_24h"]
        end = latest["ts"]
        start = end - TRAIL_HOURS * 3600
        docs = [d for d in thin(history_24h, TRAIL_STEP_S)
                if d["ts"] >= start and d.get("temp_c") is not None and d.get("rh_pct") is not None]
        trail = [[d["temp_c"], d["rh_pct"]] for d in docs]
        temp = latest.get("temp_c")
        rh = latest.get("rh_pct")
        now = [temp, rh] if latest.get("valid", {}).get("temp_humidity") and temp is not None and rh is not None else None
        c = self.comfort
        return [{
            "kind": "comfort",
            "canvas": "#comfort-chart",
            "x": {"min": 14, "max": 30},
            "y": {"min": 20, "max": 90},
            # As the trace pages draw their limits: dashed edges, and a word
            # for the side beyond each. Each edge stops where its acceptable
            # edges are, which have no line of their own.
            "area": comfort_area(c),
            "lines": comfort_lines(c),
            "xticks": [16, 20, 24, 28],
            "yticks": [30, 50, 70, 90],
            "trail": trail,
            "now": now,
        }]
