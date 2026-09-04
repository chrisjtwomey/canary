"""Barometer: pressure on an aneroid dial, with a second needle set three
hours ago so the gap between them is the tendency."""
from __future__ import annotations

from airium import Airium

from metrics import barometer_word, fmt_stamp, pressure_tendency, tendency_words, value_at
from pages.base import EnvPage

TREND_HOURS = 3
DIAL = {"min": 960, "max": 1060}
LEGENDS = [[968, "Stormy"], [988, "Rain"], [1008, "Change"], [1024, "Fair"], [1046, "Very dry"]]


class BarometerPage(EnvPage):
    title = "Barometer"
    stylesheet = "barometer.css"
    css_class = "barometer"
    requires = ("latest", "history_24h")

    def body(self, a: Airium, latest: dict, history_24h: list[dict]) -> None:
        hpa = latest.get("pressure_hpa")
        valid = bool(latest.get("valid", {}).get("pressure")) and hpa is not None
        delta = pressure_tendency(history_24h, latest, TREND_HOURS) if valid else None

        a.div(klass="title label", _t="Barometer")
        a.div(klass="stamp", _t=fmt_stamp(latest["ts"], self.tz))

        with a.div(klass="dial"):
            a.canvas(id="dial")

        with a.div(klass="stats"):
            with a.div(klass="hero" + ("" if valid else " cold"), id="pressure"):
                a.span(klass="value", _t=f"{hpa:.1f}" if hpa is not None else "—")
                a.span(klass="unit", _t="hPa")
                if not valid:
                    a.span(klass="cold-tag", _t="no reading")
            a.div(klass="verdict", _t=tendency_words(delta) if valid else "Warming up.")
            if valid:
                if delta is None:
                    a.div(klass="detail", _t=f"{barometer_word(hpa)}. Three hours of readings will show the trend.")
                else:
                    direction = "Up" if delta > 0 else "Down"
                    a.div(klass="detail", _t=(
                        f"{direction} {abs(delta):.1f} hPa in {TREND_HOURS} hours. {barometer_word(hpa)}."))

    def charts(self, latest: dict, history_24h: list[dict]) -> list[dict]:
        hpa = latest.get("pressure_hpa")
        valid = bool(latest.get("valid", {}).get("pressure")) and hpa is not None
        then = value_at(history_24h, "pressure_hpa", latest["ts"] - TREND_HOURS * 3600) if valid else None
        return [{
            "kind": "dial",
            "canvas": "#dial",
            "min": DIAL["min"],
            "max": DIAL["max"],
            "tick": 5,
            "labels": [960, 980, 1000, 1020, 1040, 1060],
            "legends": LEGENDS,
            "value": hpa if valid else None,
            "set": then,
        }]
