"""Air: the VOC index as the one number, on Bosch's scale."""
from __future__ import annotations

from airium import Airium

from metrics import (IAQ_ACCURACY, IAQ_ZONES, NO_SENSOR_TAG, NO_SENSOR_VERDICT, fmt_stamp,
                     hour_ticks, iaq_verdict, sensor_absent, series, y_range)
from pages.base import EnvPage

SPARK_HOURS = 12

# hachure gap and shade per zone: denser and darker as the air gets worse
ZONE_STYLE = {
    "excellent": (16, "#dbdbdb"),
    "good": (12, "#b6b6b6"),
    "light": (9, "#929292"),
    "moderate": (7, "#6d6d6d"),
    "heavy": (5, "#494949"),
    "severe": (4, "#242424"),
    "extreme": (3, "#000000"),
}


class AirPage(EnvPage):
    title = "Air"
    stylesheet = "air.css"
    css_class = "air"
    requires = ("latest", "history_24h", "status")

    def body(self, a: Airium, **data) -> None:
        latest: dict = data["latest"]
        history_24h: list[dict] = data["history_24h"]
        valid = bool(latest.get("valid", {}).get("gas"))
        absent = sensor_absent(data.get("status"), "bme688")
        iaq = latest.get("iaq") if valid else None
        gas = latest.get("gas_ohm") if valid else None
        accuracy = latest.get("iaq_accuracy")

        a.div(klass="title label", _t="Air quality")
        a.div(klass="stamp", _t=fmt_stamp(latest["ts"], self.tz))

        with a.div(klass="hero" + ("" if valid else " cold"), id="iaq"):
            if iaq is not None:
                a.span(klass="value", _t=f"{iaq:.0f}")
                a.span(klass="unit", _t="IAQ")
            elif gas is not None:
                a.span(klass="value", _t=f"{gas / 1000:.0f}")
                a.span(klass="unit", _t="kΩ")
            else:
                a.span(klass="value", _t="—")
                a.span(klass="unit", _t="IAQ")
            if not valid:
                a.span(klass="cold-tag", _t=NO_SENSOR_TAG if absent else "heater warming up")

        if iaq is not None:
            a.div(klass="verdict", _t=iaq_verdict(iaq))
        elif gas is not None:
            a.div(klass="verdict", _t="No index yet.")
        else:
            a.div(klass="verdict", _t=NO_SENSOR_VERDICT if absent else "Warming up.")

        parts = []
        if gas is not None and iaq is not None:
            parts.append(f"Gas resistance {gas / 1000:.0f} kΩ.")
        if iaq is not None and accuracy is not None:
            word = IAQ_ACCURACY[max(0, min(3, int(accuracy)))]
            parts.append(f"Index accuracy {word}, {int(accuracy)} of 3.")
        elif gas is not None and iaq is None:
            parts.append("The index needs the BSEC library on the board.")
        if parts:
            a.div(klass="detail", _t=" ".join(parts))

        a.div(klass="spark-label", _t=f"last {SPARK_HOURS} hours")
        with a.div(klass="spark"):
            a.canvas(id="iaq-spark")
        with a.div(klass="scale"):
            a.canvas(id="iaq-scale")

    def charts(self, **data) -> list[dict]:
        latest: dict = data["latest"]
        history_24h: list[dict] = data["history_24h"]
        end = latest["ts"]
        start = end - SPARK_HOURS * 3600
        valid = bool(latest.get("valid", {}).get("gas"))
        iaq = latest.get("iaq") if valid else None
        pts = [p for p in series(history_24h, "iaq", 300) if p[0] >= start]
        now = None
        if iaq is not None:
            pts.append([end, iaq])
            now = [end, iaq]
        zones = [{"from": lo, "to": hi, "label": name, "gap": ZONE_STYLE[name][0],
                  "color": ZONE_STYLE[name][1]} for lo, hi, name in IAQ_ZONES]
        return [
            {
                "kind": "sparkline",
                "canvas": "#iaq-spark",
                "points": pts,
                "x": {"min": start, "max": end},
                "y": y_range([v for _, v in pts], floor=0, ceil=200, pad=20),
                "guides": [{"y": 150, "label": "stale"}, {"y": 50, "label": "good"}],
                "ticks": hour_ticks(start, end, self.tz, every=3),
                "now": now,
            },
            {
                "kind": "scale",
                "canvas": "#iaq-scale",
                "min": 0,
                "max": 500,
                "zones": zones,
                "ticks": [0, 50, 100, 150, 200, 250, 350, 500],
                "value": iaq,
            },
        ]
