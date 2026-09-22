"""Diagnostics: what each board says about itself, now and over the day.

Both boards post a ``client`` object with every document. DiagnosticsPage
shows the newest from each; DiagnosticsTracePage draws both boards' free
memory and signal, and the dock's queue, over the last 24 hours, with the
restarts each counted. HealthTracePage draws the dock's ``health`` object
over the same day: how its sensors fare rather than what they measure.
"""
from __future__ import annotations

import os

from airium import Airium

import math

from metrics import (IAQ_ACCURACY, fmt_bytes, fmt_duration, fmt_int, fmt_stamp, hour_ticks,
                     rssi_quality)
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


def queue_of(c: dict) -> dict | None:
    """The board's queue, ``{"held", "capacity", "store"}``, or None for a
    board that queues nothing: the head reports an empty store."""
    backlog = c.get("backlog")
    if not isinstance(backlog, dict) or not backlog.get("store"):
        return None
    return backlog


def about(n: int) -> str:
    """A capacity to two figures, as the estimate it is: 1480 -> "~1,500"."""
    if n < 100:
        return fmt_int(n)
    digits = int(math.log10(n)) - 1
    return "~" + fmt_int(round(n, -digits))


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
                a.div(klass="detail", _t="Each posts once it connects.")
            return
        boards = status.get("boards") or {}
        for device in ordered_boards(boards):
            self._board(a, device, boards[device])

    def _board(self, a: Airium, device: str, entry: dict) -> None:
        doc = entry.get("doc") or {}
        k = board_key(device)
        c = doc.get("client") or {}
        valid = doc.get("valid") or {}
        with a.div(klass="board", id=f"board-{k}"):
            with a.div(klass="board-head"):
                a.span(klass="name label", _t=f"{k}, {c.get('board', device)}")
                age = entry.get("age_s")
                a.span(klass="stamp", id=f"{k}-age",
                       _t=f"reported {fmt_duration(age)} ago" if age is not None else "no report yet")

            with a.div(klass="card"):
                a.div(klass="label", _t="Client")
                with a.div(klass="kv"):
                    kv(a, "version", str(c.get("version", "—")), id=f"{k}-version")
                    if doc:
                        kv(a, "up", fmt_duration(c.get("uptime_s", 0)), id=f"{k}-uptime")
                    kv(a, "device", device or "—")
                    self._version_history(a, k, entry)
            if not doc:
                return

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
                queue = queue_of(c)
                if queue is not None:
                    held, capacity = queue.get("held", 0), queue.get("capacity", 0)
                    count = f"{fmt_int(held)} of {about(capacity)}" if capacity else fmt_int(held)
                    with a.div(klass="kv"):
                        kv(a, "queue", f"{count}, in {queue['store']}", id=f"{k}-queue")
                    with a.div(klass="meter"):
                        a.canvas(id=f"{k}-queue-meter")

            # The head has a panel and fetches pages; the dock has sensors. A
            # board says which it is by what it reports.
            if "sensors" in c:
                self._sensors(a, k, c, valid)
            else:
                self._panel_and_fetch(a, k, c)

    @staticmethod
    def _version_history(a: Airium, k: str, entry: dict) -> None:
        """The board's last change of version, and posts the server refused
        because of its version."""
        changed = entry.get("changed")
        if changed:
            kv(a, "downgraded" if changed["older"] else "updated",
               f"from {changed['from']}, {fmt_duration(changed['age_s'])} ago", id=f"{k}-changed")
        refused = entry.get("refused")
        if refused:
            kv(a, "refused", f"{refused['count']} from {refused['version']}, "
                             f"{fmt_duration(refused['age_s'])} ago", id=f"{k}-refused")

    def _sensors(self, a: Airium, k: str, c: dict, valid: dict) -> None:
        present = c.get("sensors") or {}
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
            doc = boards[device].get("doc")
            if not doc:
                continue
            c = doc.get("client") or {}
            rssi = c.get("rssi")
            if rssi is not None:
                specs.append({"kind": "bars", "canvas": f"#{k}-rssi-bars",
                              "filled": rssi_quality(int(rssi))[0], "total": 4})
            for key in ("heap", "psram"):
                size = c.get(f"{key}_size") or 0
                free = c.get(f"{key}_free") or 0
                specs.append({"kind": "meter", "canvas": f"#{k}-{key}-meter",
                              "fraction": (size - free) / size if size else 0.0})
            queue = queue_of(c)
            if queue is not None:
                capacity = queue.get("capacity") or 0
                specs.append({"kind": "meter", "canvas": f"#{k}-queue-meter",
                              "fraction": queue.get("held", 0) / capacity if capacity else 0.0})
        return specs


def free_memory_kb(c: dict) -> float | None:
    v = c.get("heap_free")
    return None if v is None else v / 1024


def queued(c: dict) -> float | None:
    queue = queue_of(c)
    return None if queue is None else queue.get("held")


def signal(c: dict) -> float | None:
    return c.get("rssi")


class Trace:
    """One chart of the trace page: a value from each board's client object,
    both boards on one scale.

    Args:
        key: names the canvas.
        title: the chart's label.
        value: the value from a client object, or None where it has none.
        y: a fixed axis ``(min, max)``, or None to fit the day's highest,
            no lower than ``floor``.
        step: the tick interval on a fixed axis.
        guides: ``(value, label)`` lines across the chart.
    """

    def __init__(self, key, title, value, y=None, step=0, guides=(), floor=10):
        self.key, self.title, self.value = key, title, value
        self.y, self.step, self.guides, self.floor = y, step, guides, floor

    def axis(self, highest: float) -> tuple[int, int, list[int]]:
        """``(min, max, ticks)``: the fixed axis, or one from 0 to the day's
        highest rounded up to 1, 2 or 5 of a power of ten."""
        if self.y is not None:
            lo, hi = self.y
            return lo, hi, [v for v in range(lo, hi + 1) if v % self.step == 0]
        top = max(self.floor, highest)
        power = 10 ** int(math.floor(math.log10(top)))
        top = next(m * power for m in (1, 2, 5, 10) if m * power >= top)
        return 0, int(top), [0, int(top) // 2, int(top)]


# The trace page's charts, tallest first. Free memory is what a leak shows
# in; the queue is empty unless the server was away; the signal barely moves
# once the dock is placed.
TRACES = (
    Trace("heap", "free memory, KB", free_memory_kb, y=(0, 320), step=100),
    Trace("queue", "queue, readings", queued),
    Trace("rssi", "Wi-Fi signal, dBm", signal, y=(-90, -40), step=20,
          guides=((-55, "strong"), (-75, "weak"))),
)

# Which board is the dark line when both are on a chart: the dock, which is
# the only one on the queue chart.
TRACE_ORDER = ("canary-dock", "canary-head")


class DiagnosticsTracePage(EnvPage):
    """Both boards' free memory and signal, and the dock's queue, over the
    last day, with each board's restarts."""
    title = "Diagnostics"
    stylesheet = "diagnostics-trace.css"
    css_class = "diagnostics-trace"
    requires = ("status", "status_history_24h")
    HOURS = 24

    def body(self, a: Airium, **data) -> None:
        status: dict | None = data["status"]
        history: dict = data["status_history_24h"] or {}
        a.div(klass="title label", _t="Boards, last 24 hours")
        if status is None or status.get("doc") is None:
            a.div(klass="verdict", _t="No report from either board yet.")
            a.div(klass="detail", _t="Each posts once it connects.")
            return
        a.div(klass="stamp", _t=fmt_stamp(status["doc"]["ts"], self.tz))
        boards = status.get("boards") or {}
        with a.div(klass="stats"):
            for device in ordered_boards(boards):
                k = board_key(device)
                c = (boards[device].get("doc") or {}).get("client") or {}
                n = restarts(history.get(device, []))
                with a.div(klass="stat", id=f"{k}-stat"):
                    a.span(klass="name", _t=k)
                    a.span(klass="detail", _t=(
                        f"up {fmt_duration(c.get('uptime_s', 0))}, "
                        + (f"{n} restart{'s' if n != 1 else ''} today" if n else "no restarts today")))
        with a.div(klass="charts"):
            for t in TRACES:
                with a.div(klass=f"chart chart-{t.key}"):
                    a.div(klass="label", _t=t.title)
                    a.canvas(id=f"trace-{t.key}")

    def charts(self, **data) -> list[dict]:
        status: dict | None = data["status"]
        history: dict = data["status_history_24h"] or {}
        if status is None or status.get("doc") is None:
            return []
        end = status["doc"]["ts"]
        start = end - self.HOURS * 3600
        ticks = hour_ticks(start, end, self.tz, 6)
        boards = status.get("boards") or {}
        devices = [d for d in TRACE_ORDER if d in boards] + \
                  [d for d in ordered_boards(boards) if d not in TRACE_ORDER]
        specs = []
        for t in TRACES:
            series = []
            for device in devices:
                pts = []
                for d in history.get(device, []):
                    v = t.value(d.get("client") or {})
                    if v is not None and d["ts"] >= start:
                        pts.append([d["ts"], round(v, 1)])
                if pts:
                    series.append((board_key(device), pts))
            lo, hi, yticks = t.axis(max((p[1] for _, pts in series for p in pts), default=0))
            spec = {
                "kind": "trace", "canvas": f"#trace-{t.key}",
                "points": series[0][1] if series else [],
                "x": {"min": start, "max": end}, "y": {"min": lo, "max": hi},
                "yticks": yticks,
                "guides": [{"y": g, "label": label} for g, label in t.guides],
                "days": [{"x": tick["x"]} for tick in ticks],
                "dayLabels": [{"x": tick["x"], "label": tick["label"]} for tick in ticks],
                "now": series[0][1][-1] if series else None,
            }
            if len(series) > 1:
                spec["points2"] = series[1][1]
                spec["now2"] = series[1][1][-1]
                spec["legend"] = [series[0][0], series[1][0]]
            specs.append(spec)
        return specs


def since_start(points: list[list]) -> list[list]:
    """A count the dock keeps from its own start, as the running total of
    what it added within the window. At a restart the count begins again at
    0, so what it reads then is all new."""
    out, total, before = [], 0, None
    for ts, count in points:
        if before is not None:
            total += count - before if count >= before else count
        before = count
        out.append([ts, total])
    return out


def health_value(*path):
    """The value at ``path`` in a health object, or None."""
    def get(health: dict):
        for key in path:
            health = health.get(key) if isinstance(health, dict) else None
        return health
    return get


def health_points(reports: list[dict], value, start: int) -> list[list]:
    """``[ts, value]`` from each report since ``start`` whose health object has one."""
    pts = []
    for d in reports:
        v = value(d["health"])
        if v is not None and d["ts"] >= start:
            pts.append([d["ts"], int(v)])
    return pts


# The health trace page's charts: a count added up over the day, or a flag.
HEALTH_TRACES = (
    ("restarts", "sensor restarts", health_value("restarts"), True),
    ("pmsa003i", "PMSA003I damaged frames", health_value("checksum_failures", "pmsa003i"), True),
    ("shtc3", "SHTC3 checksum failures", health_value("checksum_failures", "shtc3"), True),
    ("heater", "BME688 heater at temperature", health_value("bme688", "heat_stable"), False),
)
HEALTH_DEVICE = "canary-dock"


class HealthTracePage(EnvPage):
    """How the dock's sensors fared over the last day: restarts, damaged
    answers and the gas heater, with the SCD41's settings above them."""
    title = "Sensor health"
    stylesheet = "diagnostics-trace.css"
    css_class = "health-trace"
    requires = ("status", "status_history_24h")
    HOURS = 24

    def _dock(self, status: dict | None, history: dict) -> tuple[dict | None, list[dict]]:
        """The dock's newest health object and its reports of the day that carry one."""
        entry = ((status or {}).get("boards") or {}).get(HEALTH_DEVICE) or {}
        newest = (entry.get("doc") or {}).get("health")
        reports = [d for d in history.get(HEALTH_DEVICE, []) if isinstance(d.get("health"), dict)]
        return (newest if isinstance(newest, dict) else None), reports

    def body(self, a: Airium, **data) -> None:
        status: dict | None = data["status"]
        newest, reports = self._dock(status, data["status_history_24h"] or {})
        a.div(klass="title label", _t="Sensors, last 24 hours")
        if status is None:
            a.div(klass="verdict", _t="No report from either board yet.")
            a.div(klass="detail", _t="Each posts once it connects.")
            return
        if newest is None:
            a.div(klass="verdict", _t="No health report from the dock yet.")
            a.div(klass="detail", _t="The dock sends one with every reading.")
            return
        a.div(klass="stamp", _t=fmt_stamp(status["boards"][HEALTH_DEVICE]["doc"]["ts"], self.tz))
        end = status["boards"][HEALTH_DEVICE]["doc"]["ts"]
        added = since_start(health_points(reports, health_value("checksum_failures", "scd41"),
                                          end - self.HOURS * 3600))
        with a.div(klass="stats"):
            self._scd41(a, newest, added[-1][1] if added else 0)
        with a.div(klass="charts"):
            for key, title, _value, _counted in HEALTH_TRACES:
                with a.div(klass=f"chart chart-{key}"):
                    a.div(klass="label", _t=title)
                    a.canvas(id=f"health-{key}")

    @staticmethod
    def _scd41(a: Airium, health: dict, failures: int) -> None:
        """What the SCD41 said at its last start, which decides its accuracy,
        and its damaged answers of the day: too few to be worth a chart."""
        scd41 = health.get("scd41") or {}
        parts = [f"serial {scd41['serial']}"] if scd41.get("serial") else ["settings not read"]
        if "asc" in scd41:
            parts.append("self-calibration " + ("on" if scd41["asc"] else "off"))
        if "offset_c" in scd41:
            parts.append(f"offset {scd41['offset_c']:.1f} °C")
        parts.append(f"{failures} checksum failure{'s' if failures != 1 else ''} today")
        with a.div(klass="stat", id="scd41"):
            a.span(klass="name", _t="SCD41")
            a.span(klass="detail", _t=", ".join(parts))

    def charts(self, **data) -> list[dict]:
        status: dict | None = data["status"]
        newest, reports = self._dock(status, data["status_history_24h"] or {})
        if newest is None:
            return []
        end = status["boards"][HEALTH_DEVICE]["doc"]["ts"]
        start = end - self.HOURS * 3600
        ticks = hour_ticks(start, end, self.tz, 6)
        specs = []
        for key, _title, value, counted in HEALTH_TRACES:
            pts = health_points(reports, value, start)
            if counted:
                pts = since_start(pts)
                lo, hi, yticks = Trace(key, "", None).axis(max((p[1] for p in pts), default=0))
            else:
                lo, hi, yticks = 0, 1, [0, 1]
            specs.append({
                "kind": "trace", "canvas": f"#health-{key}", "points": pts, "step": True,
                "x": {"min": start, "max": end}, "y": {"min": lo, "max": hi},
                "yticks": yticks, "guides": [],
                "days": [{"x": t["x"]} for t in ticks],
                "dayLabels": [{"x": t["x"], "label": t["label"]} for t in ticks],
                "now": pts[-1] if pts else None,
            })
        return specs
