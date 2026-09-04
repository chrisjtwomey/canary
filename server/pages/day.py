"""Day: the last 24 hours of four measurements as stacked ribbons."""
from __future__ import annotations

from airium import Airium

from metrics import extremes, fmt_hm, fmt_int, fmt_stamp, hour_ticks, night_spans, series, y_range
from pages.base import EnvPage

WINDOW_HOURS = 24
STEP_S = 300

# key, name, unit, value formatter, y-range keywords
ROWS = (
    ("co2_ppm", "Carbon dioxide", "ppm", fmt_int, {"floor": 400, "ceil": 1200}),
    ("pm2_5", "Fine dust", "µg/m³", fmt_int, {"floor": 0, "ceil": 20}),
    ("temp_c", "Temperature", "°C", lambda v: f"{v:.1f}", {"pad": 1.0}),
    ("rh_pct", "Humidity", "%", lambda v: f"{v:.0f}", {"pad": 5.0}),
)


class DayPage(EnvPage):
    title = "Day"
    stylesheet = "day.css"
    css_class = "day"
    requires = ("latest", "history_24h")

    def body(self, a: Airium, latest: dict, history_24h: list[dict]) -> None:
        with a.div(klass="head-now"):
            a.div(klass="label", _t="Current")
        with a.div(klass="head-hist"):
            a.div(klass="label", _t=f"Last {WINDOW_HOURS} hours")
            a.div(klass="stamp", _t=fmt_stamp(latest["ts"], self.tz))
        for key, name, unit, fmt, _ in ROWS:
            value = latest.get(key)
            lo, hi = extremes(history_24h + [latest], key)
            with a.div(klass="now"):
                a.div(klass="label", _t=name)
                with a.div(klass="hero", id=f"now-{key}"):
                    a.span(klass="value", _t=fmt(value) if value is not None else "—")
                    a.span(klass="unit", _t=unit)
            with a.div(klass="hist"):
                with a.div(klass="range", id=f"range-{key}"):
                    for tag, doc in (("high", hi), ("low", lo)):
                        if doc is None:
                            continue
                        a.span(klass="tag", _t=tag)
                        a.span(klass="v", _t=fmt(doc[key]))
                        a.span(klass="t", _t=fmt_hm(doc["ts"], self.tz))
                with a.div(klass="chart"):
                    a.canvas(id=f"rib-{key}")
        with a.div(klass="hist axis"):
            a.div(klass="spacer")
            with a.div(klass="chart"):
                a.canvas(id="rib-axis")

    def charts(self, latest: dict, history_24h: list[dict]) -> list[dict]:
        end = latest["ts"]
        start = end - WINDOW_HOURS * 3600
        window = {"min": start, "max": end}
        nights = night_spans(start, end, self.tz)
        specs = []
        for key, _, _, _, rng in ROWS:
            pts = [p for p in series(history_24h, key, STEP_S) if p[0] >= start]
            value = latest.get(key)
            if value is not None:
                pts.append([end, value])
            specs.append({
                "kind": "ribbon",
                "canvas": f"#rib-{key}",
                "points": pts,
                "x": window,
                "y": y_range([v for _, v in pts], **rng),
                "nights": nights,
                "now": [end, value] if value is not None else None,
            })
        specs.append({
            "kind": "axis",
            "canvas": "#rib-axis",
            "x": window,
            "ticks": hour_ticks(start, end, self.tz, every=6),
        })
        return specs
