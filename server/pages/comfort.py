"""Comfort: temperature and humidity as one point on the comfort chart."""
from __future__ import annotations

from airium import Airium

from metrics import (ACCEPTABLE_RH, ACCEPTABLE_T, COMFORT_RH, COMFORT_T, abs_humidity_g_m3,
                     comfort_verdict, dew_point_c, fmt_stamp, thin)
from pages.base import EnvPage

TRAIL_HOURS = 6
TRAIL_STEP_S = 600


class ComfortPage(EnvPage):
    title = "Comfort"
    stylesheet = "comfort.css"
    css_class = "comfort"
    requires = ("latest", "history_24h")

    def body(self, a: Airium, latest: dict, history_24h: list[dict]) -> None:
        temp = latest.get("temp_c")
        rh = latest.get("rh_pct")
        valid = bool(latest.get("valid", {}).get("temp_humidity")) and temp is not None and rh is not None

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
                        a.span(klass="cold-tag", _t="warming up")
                a.div(klass="label", _t="Temperature")
            with a.div(klass="stat"):
                with a.div(klass="hero" + ("" if valid else " cold"), id="rh"):
                    a.span(klass="value", _t=f"{rh:.0f}" if rh is not None else "—")
                    a.span(klass="unit", _t="%")
                a.div(klass="label", _t="Humidity")
            verdict = "Warming up."
            if valid:
                assert temp is not None and rh is not None   # what valid means
                a.div(klass="detail", _t=(
                    f"Dew point {dew_point_c(temp, rh):.1f}°, "
                    f"vapour {abs_humidity_g_m3(temp, rh):.1f} g/m³."))
                verdict = comfort_verdict(temp, rh)
            extra = self.extra_detail(latest, history_24h)
            if extra:
                a.div(klass="detail", _t=extra)
            a.div(klass="verdict", _t=verdict)

    def extra_detail(self, latest: dict, history_24h: list[dict]) -> str | None:
        return None

    def charts(self, latest: dict, history_24h: list[dict]) -> list[dict]:
        end = latest["ts"]
        start = end - TRAIL_HOURS * 3600
        docs = [d for d in thin(history_24h, TRAIL_STEP_S)
                if d["ts"] >= start and d.get("temp_c") is not None and d.get("rh_pct") is not None]
        trail = [[d["temp_c"], d["rh_pct"]] for d in docs]
        temp = latest.get("temp_c")
        rh = latest.get("rh_pct")
        now = [temp, rh] if latest.get("valid", {}).get("temp_humidity") and temp is not None and rh is not None else None
        return [{
            "kind": "comfort",
            "canvas": "#comfort-chart",
            "x": {"min": 14, "max": 30},
            "y": {"min": 20, "max": 80},
            "zones": [
                {"t": list(ACCEPTABLE_T), "rh": list(ACCEPTABLE_RH), "gap": 13, "color": "#b6b6b6"},
                {"t": list(COMFORT_T), "rh": list(COMFORT_RH), "gap": 6, "color": "#6d6d6d"},
            ],
            "xticks": [16, 20, 24, 28],
            "yticks": [30, 50, 70],
            "trail": trail,
            "now": now,
        }]
