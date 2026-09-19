"""Diagnostics: what each board says about itself, now and over the day.

Both boards post a ``client`` object once a minute. DiagnosticsPage shows
the newest from each; DiagnosticsTracePage draws each board's signal and
free memory over the last 24 hours, with the restarts it counted.
"""
from __future__ import annotations

import os

from airium import Airium

from metrics import IAQ_ACCURACY, fmt_bytes, fmt_duration, fmt_stamp, hour_ticks, rssi_quality
from pages.base import EnvPage

# key in client.sensors, its name, and the valid flag that says it is warm
SENSORS = (
    ("shtc3", "SHTC3", "temp_humidity"),
    ("scd41", "SCD41", "co2"),
    ("pmsa003i", "PMSA003I", "particulates"),
    ("bme688", "BME688", "gas"),
)

# The boards in the order the pages show them; anything else follows.
BOARD_ORDER = ("canary-head", "canary-dock")


def board_key(device: str) -> str:
    """The short name the page keys ids on: ``canary-head`` -> ``head``."""
    return device.rsplit("-", 1)[-1] if device else "board"


def ordered_boards(boards: dict) -> list[str]:
    known = [d for d in BOARD_ORDER if d in boards]
    return known + [d for d in boards if d not in known]


def restarts(history: list[dict]) -> int:
    """How many times the uptime fell between consecutive reports."""
    ups = [d["client"].get("uptime_s") for d in history if isinstance(d.get("client"), dict)]
    ups = [u for u in ups if u is not None]
    return sum(1 for a, b in zip(ups, ups[1:]) if b < a)


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
        with a.div(klass="head"):
            a.div(klass="title label", _t="Boards")
            if status is not None:
                a.div(klass="stamp", _t=f"{status['count']} reports")
        if status is None:
            with a.div(klass="empty"):
                a.div(klass="verdict", _t="No report from either board yet.")
                a.div(klass="detail", _t="Each posts to /readings once a minute after it connects.")
            return
        boards = status.get("boards") or {}
        for device in ordered_boards(boards):
            self._board(a, device, boards[device])

    def _board(self, a: Airium, device: str, entry: dict) -> None:
        doc = entry["doc"]
        k = board_key(device)
        c = doc.get("client") or {}
        valid = doc.get("valid") or {}
        with a.div(klass="board", id=f"board-{k}"):
            with a.div(klass="board-head"):
                a.span(klass="name label", _t=f"{k}, {c.get('board', device)}")
                a.span(klass="stamp", _t=f"reported {fmt_duration(entry['age_s'])} ago", id=f"{k}-age")

            with a.div(klass="card"):
                a.div(klass="label", _t="Client")
                with a.div(klass="kv"):
                    kv(a, "version", str(c.get("version", "—")), id=f"{k}-version")
                    kv(a, "up", fmt_duration(c.get("uptime_s", 0)), id=f"{k}-uptime")
                    kv(a, "device", device or "—")

            with a.div(klass="card"):
                a.div(klass="label", _t="Network")
                rssi = c.get("rssi")
                with a.div(klass="kv"):
                    kv(a, "address", str(c.get("ip", "—")), id=f"{k}-ip")
                    if rssi is not None:
                        bars, word = rssi_quality(int(rssi))
                        kv(a, "signal", f"{rssi} dBm, {word}", id=f"{k}-rssi")
                with a.div(klass="bars"):
                    a.canvas(id=f"{k}-rssi-bars")

            with a.div(klass="card"):
                a.div(klass="label", _t="Memory")
                with a.div(klass="kv"):
                    kv(a, "heap", f"{fmt_bytes(c.get('heap_free', 0))} free of {fmt_bytes(c.get('heap_size', 0))}", id=f"{k}-heap")
                with a.div(klass="meter"):
                    a.canvas(id=f"{k}-heap-meter")
                with a.div(klass="kv"):
                    kv(a, "psram", f"{fmt_bytes(c.get('psram_free', 0))} free of {fmt_bytes(c.get('psram_size', 0))}", id=f"{k}-psram")
                with a.div(klass="meter"):
                    a.canvas(id=f"{k}-psram-meter")

            # The head has a panel and fetches pages; the dock has sensors and
            # a backlog. A board says which it is by what it reports.
            if "sensors" in c:
                self._sensors(a, k, c, valid)
            else:
                self._panel_and_fetch(a, k, c)

    def _sensors(self, a: Airium, k: str, c: dict, valid: dict) -> None:
        present = c.get("sensors") or {}
        backlog = c.get("backlog")
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
                    kv(a, name, state, id=f"{k}-sensor-{key}")
                bsec = c.get("bsec") or {}
                if bsec.get("running"):
                    word = IAQ_ACCURACY[max(0, min(3, int(bsec.get("accuracy", 0))))]
                    kv(a, "index", f"{word} accuracy, {bsec.get('late', 0)} late", id=f"{k}-bsec")
                if backlog is not None:
                    held = backlog.get("held", 0)
                    store = backlog.get("store") or "nowhere"
                    kv(a, "unsent", f"{held}, in {store}" if held else "none", id=f"{k}-backlog")

    def _panel_and_fetch(self, a: Airium, k: str, c: dict) -> None:
        fetch = c.get("fetch") or {}
        with a.div(klass="card"):
            a.div(klass="label", _t="Panel and fetch")
            with a.div(klass="kv"):
                kv(a, "pixels", f"{c.get('width', '—')} × {c.get('height', '—')}, 8 greys")
                temp = c.get("panel_temp_c")
                kv(a, "controller", f"{temp} °C" if temp is not None else "—", id=f"{k}-panel-temp")
                url = fetch.get("next_url") or ""
                kv(a, "next", os.path.basename(url) or "—", id=f"{k}-next-page")
                kv(a, "in", fmt_duration(fetch.get("next_in_s", 0)))
                kv(a, "fetched", f"{fetch.get('ok', 0)} ok, {fetch.get('failed', 0)} failed", id=f"{k}-fetches")
                step = fetch.get("backoff_step", 0)
                kv(a, "back-off", f"step {step}" if step else "none")

    def charts(self, **data) -> list[dict]:
        status: dict | None = data["status"]
        if status is None:
            return []
        specs = []
        boards = status.get("boards") or {}
        for device in ordered_boards(boards):
            k = board_key(device)
            c = boards[device]["doc"].get("client") or {}
            rssi = c.get("rssi")
            if rssi is not None:
                specs.append({"kind": "bars", "canvas": f"#{k}-rssi-bars",
                              "filled": rssi_quality(int(rssi))[0], "total": 4})
            for key in ("heap", "psram"):
                size = c.get(f"{key}_size") or 0
                free = c.get(f"{key}_free") or 0
                specs.append({"kind": "meter", "canvas": f"#{k}-{key}-meter",
                              "fraction": (size - free) / size if size else 0.0})
        return specs


# What the trace page draws for each board: the client key, the chart's
# title, how the value is scaled, its axis range and the guides on it.
TRACES = (
    ("rssi", "Wi-Fi signal, dBm", 1.0, (-95, -30), ((-55, "strong"), (-75, "weak")), 10),
    ("heap_free", "free memory, KB", 1 / 1024, (0, 320), (), 100),
)


class DiagnosticsTracePage(EnvPage):
    """Each board's signal and free memory over the last day, and its restarts."""
    title = "Diagnostics"
    stylesheet = "diagnostics-trace.css"
    css_class = "diagnostics-trace"
    requires = ("status", "status_history_24h")
    HOURS = 24

    def body(self, a: Airium, **data) -> None:
        status: dict | None = data["status"]
        history: dict = data["status_history_24h"] or {}
        a.div(klass="title label", _t="Boards, last 24 hours")
        if status is None:
            a.div(klass="verdict", _t="No report from either board yet.")
            a.div(klass="detail", _t="Each posts to /readings once a minute after it connects.")
            return
        a.div(klass="stamp", _t=fmt_stamp(status["doc"]["ts"], self.tz))
        boards = status.get("boards") or {}
        with a.div(klass="stats"):
            for device in ordered_boards(boards):
                k = board_key(device)
                c = boards[device]["doc"].get("client") or {}
                n = restarts(history.get(device, []))
                with a.div(klass="stat", id=f"{k}-stat"):
                    a.span(klass="name", _t=k)
                    a.span(klass="detail", _t=(
                        f"up {fmt_duration(c.get('uptime_s', 0))}, "
                        + (f"{n} restart{'s' if n != 1 else ''} today" if n else "no restarts today")))
        with a.div(klass="charts"):
            for key, title, _scale, _rng, _guides, _step in TRACES:
                for device in ordered_boards(boards):
                    k = board_key(device)
                    with a.div(klass="chart"):
                        a.div(klass="label", _t=f"{k}, {title}")
                        a.canvas(id=f"{k}-{key}")

    def charts(self, **data) -> list[dict]:
        status: dict | None = data["status"]
        history: dict = data["status_history_24h"] or {}
        if status is None:
            return []
        end = status["doc"]["ts"]
        start = end - self.HOURS * 3600
        ticks = hour_ticks(start, end, self.tz, 6)
        boards = status.get("boards") or {}
        specs = []
        for key, _title, scale, (lo, hi), guides, step in TRACES:
            for device in ordered_boards(boards):
                k = board_key(device)
                pts = []
                for d in history.get(device, []):
                    v = (d.get("client") or {}).get(key)
                    if v is not None and d["ts"] >= start:
                        pts.append([d["ts"], round(v * scale, 1)])
                now = pts[-1] if pts else None
                specs.append({
                    "kind": "trace", "canvas": f"#{k}-{key}", "points": pts,
                    "x": {"min": start, "max": end}, "y": {"min": lo, "max": hi},
                    "yticks": [v for v in range(lo, hi + 1) if v % step == 0],
                    "guides": [{"y": g, "label": label} for g, label in guides],
                    "days": [{"x": t["x"]} for t in ticks],
                    "dayLabels": [{"x": t["x"], "label": t["label"]} for t in ticks],
                    "now": now,
                })
        return specs
