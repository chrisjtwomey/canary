"""Diagnostics: what the board says about itself in its last report."""
from __future__ import annotations

import os

from airium import Airium

from metrics import fmt_bytes, fmt_duration, rssi_quality
from pages.base import EnvPage

# key in client.sensors, its name, and the valid flag that says it is warm
SENSORS = (
    ("shtc3", "SHTC3", "temp_humidity"),
    ("scd41", "SCD41", "co2"),
    ("pmsa003i", "PMSA003I", "particulates"),
    ("bme688", "BME688", "gas"),
)


def kv(a: Airium, key: str, value: str, id: str | None = None) -> None:
    a.span(klass="k", _t=key)
    # Airium writes a None attribute as id="null", so an unnamed row would
    # carry an id, and every unnamed row would carry the same one.
    if id is None:
        a.span(klass="v", _t=value)
    else:
        a.span(klass="v", id=id, _t=value)


class DiagnosticsPage(EnvPage):
    title = "Diagnostics"
    stylesheet = "diagnostics.css"
    css_class = "diagnostics"
    requires = ("status",)

    def body(self, a: Airium, **data) -> None:
        status: dict | None = data["status"]
        if status is None:
            with a.div(klass="head"):
                a.div(klass="title label", _t="Inkplate")
            with a.div(klass="empty"):
                a.div(klass="verdict", _t="No report from the board yet.")
                a.div(klass="detail", _t="It posts to /readings once a minute after it connects.")
            return

        doc = status["doc"]
        c = doc.get("client") or {}
        valid = doc.get("valid") or {}
        present = c.get("sensors") or {}
        fetch = c.get("fetch") or {}
        backlog = c.get("backlog")

        with a.div(klass="head"):
            a.div(klass="title label", _t=c.get("board", "Inkplate"))
            a.div(klass="stamp", _t=f"reported {fmt_duration(status['age_s'])} ago, report {status['count']}")

        with a.div(klass="card"):
            a.div(klass="label", _t="Client")
            with a.div(klass="kv"):
                kv(a, "version", str(c.get("version", "—")), id="version")
                kv(a, "up", fmt_duration(c.get("uptime_s", 0)), id="uptime")
                kv(a, "sensors", "mocks" if c.get("mock_sensors") else "real", id="mock")
                kv(a, "device", str(doc.get("device", "—")))

        with a.div(klass="card"):
            a.div(klass="label", _t="Network")
            rssi = c.get("rssi")
            with a.div(klass="kv"):
                kv(a, "address", str(c.get("ip", "—")), id="ip")
                if rssi is not None:
                    bars, word = rssi_quality(int(rssi))
                    kv(a, "signal", f"{rssi} dBm, {word}", id="rssi")
            with a.div(klass="bars"):
                a.canvas(id="rssi-bars")

        with a.div(klass="card"):
            a.div(klass="label", _t="Memory")
            with a.div(klass="kv"):
                kv(a, "heap", f"{fmt_bytes(c.get('heap_free', 0))} free of {fmt_bytes(c.get('heap_size', 0))}", id="heap")
            with a.div(klass="meter"):
                a.canvas(id="heap-meter")
            with a.div(klass="kv"):
                kv(a, "psram", f"{fmt_bytes(c.get('psram_free', 0))} free of {fmt_bytes(c.get('psram_size', 0))}", id="psram")
            with a.div(klass="meter"):
                a.canvas(id="psram-meter")

        with a.div(klass="card"):
            a.div(klass="label", _t="Panel")
            with a.div(klass="kv"):
                kv(a, "pixels", f"{c.get('width', '—')} × {c.get('height', '—')}, 8 greys")
                kv(a, "rotation", str(c.get("rotation", "—")))
                temp = c.get("panel_temp_c")
                kv(a, "controller", f"{temp} °C" if temp is not None else "—", id="panel-temp")

        with a.div(klass="card"):
            a.div(klass="label", _t="Sensors")
            with a.div(klass="kv"):
                for key, name, flag in SENSORS:
                    if not present.get(key):
                        state = "missing"
                    elif valid.get(flag):
                        state = "ok"
                    else:
                        state = "warming up"
                    kv(a, name, state, id=f"sensor-{key}")

        with a.div(klass="card"):
            a.div(klass="label", _t="Fetch")
            with a.div(klass="kv"):
                url = fetch.get("next_url") or ""
                kv(a, "next", os.path.basename(url) or "—", id="next-page")
                kv(a, "in", fmt_duration(fetch.get("next_in_s", 0)))
                kv(a, "fetched", f"{fetch.get('ok', 0)} ok, {fetch.get('failed', 0)} failed", id="fetches")
                step = fetch.get("backoff_step", 0)
                kv(a, "back-off", f"step {step}" if step else "none")
                if backlog is not None:
                    held = backlog.get("held", 0)
                    store = backlog.get("store") or "nowhere"
                    kv(a, "unsent", f"{held}, in {store}" if held else "none", id="backlog")

    def charts(self, **data) -> list[dict]:
        status: dict | None = data["status"]
        if status is None:
            return []
        c = status["doc"].get("client") or {}
        specs = []
        rssi = c.get("rssi")
        if rssi is not None:
            specs.append({"kind": "bars", "canvas": "#rssi-bars", "filled": rssi_quality(int(rssi))[0], "total": 4})
        for key, canvas in (("heap", "#heap-meter"), ("psram", "#psram-meter")):
            size = c.get(f"{key}_size") or 0
            free = c.get(f"{key}_free") or 0
            specs.append({"kind": "meter", "canvas": canvas,
                          "fraction": (size - free) / size if size else 0.0})
        return specs
