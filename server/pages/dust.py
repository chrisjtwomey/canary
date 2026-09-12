"""Dust: PM2.5 as the one number, and the particle counts drawn as a cloud."""
from __future__ import annotations

from airium import Airium

from metrics import (NO_SENSOR_TAG, NO_SENSOR_VERDICT, extremes, fmt_hm, fmt_int, fmt_stamp,
                     pm25_verdict, sensor_absent)
from pages.base import EnvPage

# key, size label, dots per particle counted, dot radius, shade, hand-drawn
BINS = (
    ("pc_0_3", "0.3", 0.08, 1.3, "#929292", False),
    ("pc_0_5", "0.5", 0.20, 1.9, "#6d6d6d", False),
    ("pc_1_0", "1", 0.60, 2.7, "#494949", False),
    ("pc_2_5", "2.5", 2.00, 4.0, "#242424", False),
    ("pc_5_0", "5", 4.00, 6.0, "#000000", False),
    ("pc_10", "10", 8.00, 9.0, "#000000", True),
)
MAX_DOTS = 2500


def cloud_dots(latest: dict) -> list[dict]:
    """One entry per size bin: how many dots to draw and how."""
    dots = []
    for key, _, per, r, color, rough in BINS:
        n = latest.get(key)
        if n is None:
            continue
        dots.append({"n": int(round(n * per)), "r": r, "color": color, "rough": rough})
    total = sum(d["n"] for d in dots)
    if total > MAX_DOTS:
        for d in dots:
            d["n"] = int(round(d["n"] * MAX_DOTS / total))
    return dots


class DustPage(EnvPage):
    title = "Dust"
    stylesheet = "dust.css"
    css_class = "dust"
    requires = ("latest", "history_24h", "status")

    def body(self, a: Airium, **data) -> None:
        latest: dict = data["latest"]
        history_24h: list[dict] = data["history_24h"]
        pm25 = latest.get("pm2_5")
        valid = bool(latest.get("valid", {}).get("particulates")) and pm25 is not None
        absent = sensor_absent(data.get("status"), "pmsa003i")
        lo, hi = extremes(history_24h + [latest], "pm2_5")

        a.div(klass="title label", _t="Fine dust")
        a.div(klass="stamp", _t=fmt_stamp(latest["ts"], self.tz))

        with a.div(klass="hero" + ("" if valid else " cold"), id="pm25"):
            a.span(klass="value", _t=fmt_int(pm25) if pm25 is not None else "—")
            a.span(klass="unit", _t="µg/m³")
            if not valid:
                a.span(klass="cold-tag", _t=NO_SENSOR_TAG if absent else "fan warming up")

        if valid:
            assert pm25 is not None   # which is part of what valid means
            a.div(klass="verdict", _t=pm25_verdict(pm25))
        else:
            a.div(klass="verdict", _t=NO_SENSOR_VERDICT if absent else "Warming up.")

        parts = []
        if valid:
            parts.append(f"PM1 {fmt_int(latest.get('pm1_0', 0))} · PM10 {fmt_int(latest.get('pm10', 0))}.")
        if hi:
            parts.append(f"High of {fmt_int(hi['pm2_5'])} at {fmt_hm(hi['ts'], self.tz)}.")
        if parts:
            a.div(klass="detail", _t=" ".join(parts))

        with a.div(klass="cloud"):
            a.canvas(id="dust-cloud")
        if valid and latest.get("pc_0_3") is not None:
            a.div(klass="caption", _t=(
                f"{fmt_int(latest['pc_0_3'])} particles over 0.3 µm in a tenth of a litre"))
        elif not valid and not absent:
            a.div(klass="caption", _t="the fan needs thirty seconds before the counts mean anything")

    def charts(self, **data) -> list[dict]:
        latest: dict = data["latest"]
        history_24h: list[dict] = data["history_24h"]
        valid = bool(latest.get("valid", {}).get("particulates"))
        return [{
            "kind": "dotcloud",
            "canvas": "#dust-cloud",
            "seed": 7,
            "dots": cloud_dots(latest) if valid else [],
        }]
