"""Breathe: CO2 as the one number, with a verdict and the last three hours."""
from __future__ import annotations

from airium import Airium

from metrics import (co2_verdict, extremes, fmt_duration, fmt_hm, fmt_int, fmt_stamp, hour_ticks,
                     local_midnight, minutes_above, series, ventilation_events, y_range)
from pages.base import EnvPage

SPARK_HOURS = 3
STUFFY_PPM = 1000


class BreathePage(EnvPage):
    title = "Breathe"
    stylesheet = "breathe.css"
    css_class = "breathe"
    requires = ("latest", "history_24h")

    def body(self, a: Airium, **data) -> None:
        latest: dict = data["latest"]
        history_24h: list[dict] = data["history_24h"]
        co2 = latest.get("co2_ppm")
        valid = bool(latest.get("valid", {}).get("co2")) and co2 is not None
        lo, hi = extremes(history_24h + [latest], "co2_ppm")

        a.div(klass="title label", _t="Carbon dioxide")
        a.div(klass="stamp", _t=fmt_stamp(latest["ts"], self.tz))

        with a.div(klass="hero" + ("" if valid else " cold"), id="co2"):
            a.span(klass="value", _t=fmt_int(co2) if co2 is not None else "—")
            a.span(klass="unit", _t="ppm")
            if not valid:
                a.span(klass="cold-tag", _t="warming up")

        if valid:
            assert co2 is not None   # which is part of what valid means
            a.div(klass="verdict", _t=co2_verdict(co2))
        else:
            a.div(klass="verdict", _t="Warming up.")

        with a.div(klass="details"):
            if lo and hi:
                a.div(klass="detail", _t=self._extremes_line(latest, lo, hi))
            a.div(klass="detail", id="today", _t=self._today_line(latest, history_24h))

        a.div(klass="spark-label", _t=f"last {SPARK_HOURS} hours")
        with a.div(klass="spark"):
            a.canvas(id="co2-spark")

        with a.div(klass="footer"):
            temp = latest.get("temp_c")
            rh = latest.get("rh_pct")
            if temp is not None and rh is not None:
                a.span(_t=f"{temp:.1f}° · {rh:.0f} %")

    def _today_line(self, latest: dict, history: list[dict]) -> str:
        since = local_midnight(latest["ts"], self.tz)
        stuffy = minutes_above(history + [latest], "co2_ppm", STUFFY_PPM, since)
        aired = [t for t in ventilation_events(history) if t >= since]
        first = (f"Above {fmt_int(STUFFY_PPM)} ppm for {fmt_duration(stuffy * 60)} today."
                 if stuffy else f"Not above {fmt_int(STUFFY_PPM)} ppm today.")
        if not aired:
            return f"{first} Not aired yet."
        times = " and ".join(fmt_hm(t, self.tz) for t in aired)
        return f"{first} Aired at {times}."

    def _extremes_line(self, latest: dict, lo: dict, hi: dict) -> str:
        high = f"High of {fmt_int(hi['co2_ppm'])} at {fmt_hm(hi['ts'], self.tz)}."
        low = f"Low of {fmt_int(lo['co2_ppm'])} at {fmt_hm(lo['ts'], self.tz)}."
        if hi is latest:
            return f"Now at the day's high. {low}"
        if lo is latest:
            return f"Now at the day's low. {high}"
        return f"{high} {low}"

    def charts(self, **data) -> list[dict]:
        latest: dict = data["latest"]
        history_24h: list[dict] = data["history_24h"]
        end = latest["ts"]
        start = end - SPARK_HOURS * 3600
        pts = [p for p in series(history_24h, "co2_ppm", 120) if p[0] >= start]
        co2 = latest.get("co2_ppm")
        now = None
        if co2 is not None and latest.get("valid", {}).get("co2"):
            pts.append([end, co2])
            now = [end, co2]
        return [{
            "kind": "sparkline",
            "canvas": "#co2-spark",
            "points": pts,
            "x": {"min": start, "max": end},
            "y": y_range([v for _, v in pts], floor=400, ceil=1200, pad=60),
            "guides": [{"y": 1000, "label": "stuffy"}, {"y": 700, "label": "fresh"}],
            "ticks": hour_ticks(start, end, self.tz, every=1),
            "now": now,
        }]
