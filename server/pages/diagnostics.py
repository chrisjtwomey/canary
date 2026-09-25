"""Diagnostics: what each board says about itself, now and over the day.

Both boards post a ``client`` object with every document. DiagnosticsPage
shows the newest from each; DiagnosticsTracePage draws both boards' free
memory, and the dock's queue, over the last 24 hours, with the restarts each
counted. HealthTracePage draws the dock's ``health`` object
over the same day: how its sensors fare rather than what they measure.
"""
from __future__ import annotations

import os
from datetime import datetime

from airium import Airium
from markupsafe import Markup

import math

from metrics import (IAQ_ACCURACY, age_span, fmt_bytes, fmt_duration, fmt_hm, fmt_int, fmt_stamp,
                     hour_ticks, in_span, rssi_quality)
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


# The reasons a board gives for its start (the client object's "reset") that
# are faults: a crash, a watchdog, a power dip.
FAULT_STARTS = {"panic", "cpu_lockup", "int_watchdog", "task_watchdog", "watchdog", "brownout",
                "power_glitch", "efuse"}


def restarts(history: list[dict]) -> tuple[int, int]:
    """How many times the uptime fell between consecutive reports, and how
    many of those a fault caused. A wake from deep sleep is no restart."""
    starts = [(d["client"].get("uptime_s"), d["client"].get("reset")) for d in history
              if isinstance(d.get("client"), dict) and d["client"].get("uptime_s") is not None]
    fell = [reset for (a, _), (b, reset) in zip(starts, starts[1:])
            if b < a and reset != "deep_sleep"]
    return len(fell), sum(1 for reset in fell if reset in FAULT_STARTS)


def queue_of(c: dict) -> dict | None:
    """The board's queue, ``{"held", "capacity", "store"}``, or None for a
    board that queues nothing: the head reports an empty store."""
    backlog = (c.get("dock") or {}).get("backlog")
    if not isinstance(backlog, dict) or not backlog.get("store"):
        return None
    return backlog


def about(n: int) -> str:
    """A capacity to two figures, as the estimate it is: 1480 -> "~1,500"."""
    if n < 100:
        return fmt_int(n)
    digits = int(math.log10(n)) - 1
    return "~" + fmt_int(round(n, -digits))


def kv(a: Airium, key: str, value: str, id: str | None = None, sub: bool = False) -> None:
    """One row. ``sub`` sets it under the row before it, as a detail of that one."""
    a.span(klass="k sub" if sub else "k", _t=key)
    klass = "v sub" if sub else "v"
    # Airium writes a None attribute as id="null", so an unnamed row would
    # carry an id, and every unnamed row would carry the same one.
    if id is None:
        a.span(klass=klass, _t=value)
    else:
        a.span(klass=klass, id=id, _t=value)


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
                with a.span(klass="when"):
                    if entry.get("offline"):
                        a.span(klass="pill offline", id=f"{k}-offline", _t="Offline")
                    a.span(klass="stamp", id=f"{k}-age",
                           _t=Markup("reported {} ago").format(age_span(age)) if age is not None
                           else "no report yet")

            with a.div(klass="card"):
                a.div(klass="label", _t="Client")
                with a.div(klass="kv"):
                    kv(a, "version", str(c.get("version", "—")), id=f"{k}-version")
                    if doc:
                        kv(a, "up", fmt_duration(c.get("uptime_s", 0)), id=f"{k}-uptime")
                        if c.get("chip_temp_c") is not None:
                            kv(a, "chip", f"{c['chip_temp_c']} °C", id=f"{k}-chip-temp")
                    self._refused(a, k, entry)
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
                self._memory(a, k, c)

            if isinstance(c.get("dock"), dict):
                self._sensors(a, k, c["dock"], valid, entry.get("next_post_s"))
            elif isinstance(c.get("head"), dict):
                self._panel(a, k, c["head"], entry.get("age_s") or 0)

    @staticmethod
    def _memory(a: Airium, k: str, c: dict) -> None:
        """The board's memory, and the dock's queue."""
        a.div(klass="label", _t="Memory")
        with a.div(klass="kv"):
            kv(a, "heap", f"{fmt_bytes(c.get('heap_free', 0))} free of {fmt_bytes(c.get('heap_size', 0))}", id=f"{k}-heap")
        with a.div(klass="meter"):
            a.canvas(id=f"{k}-heap-meter")
        if c.get("psram_size"):
            with a.div(klass="kv"):
                kv(a, "psram", f"{fmt_bytes(c.get('psram_free', 0))} free of {fmt_bytes(c['psram_size'])}", id=f"{k}-psram")
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

    @staticmethod
    def _refused(a: Airium, k: str, entry: dict) -> None:
        """Posts the server refused because of the board's version."""
        refused = entry.get("refused")
        if refused:
            kv(a, "refused", Markup("{} from {}, {} ago").format(
                refused["count"], refused["version"], age_span(refused["age_s"])), id=f"{k}-refused")

    def _sensors(self, a: Airium, k: str, dock: dict, valid: dict, next_post_s: int | None) -> None:
        """When the dock reports next, then each sensor, with the PM fan's mode
        and BSEC's accuracy under the sensor each belongs to."""
        present = dock.get("sensors") or {}
        bsec = dock.get("bsec") or {}
        with a.div(klass="card"):
            a.div(klass="label", _t="Sensors")
            with a.div(klass="kv"):
                if next_post_s is not None:
                    kv(a, "next report", in_span(next_post_s), id=f"{k}-next-report")
                for key, name, flag in SENSORS:
                    if not present.get(key):
                        state = "missing"
                    elif valid.get(flag):
                        state = "ok"
                    else:
                        state = "warming up"
                    kv(a, name, state, id=f"{k}-sensor-{key}")
                    if key == "pmsa003i" and dock.get("fan_warmup_s") is not None:
                        warmup = dock["fan_warmup_s"]
                        kv(a, "fan", f"{warmup} s warm-up" if warmup else "always on",
                           id=f"{k}-fan", sub=True)
                    if key == "bme688" and bsec.get("running"):
                        word = IAQ_ACCURACY[max(0, min(3, int(bsec.get("accuracy", 0))))]
                        kv(a, "accuracy", word, id=f"{k}-bsec", sub=True)

    @staticmethod
    def _panel(a: Airium, k: str, head: dict, age_s: int) -> None:
        """The head's panel and its fetches. ``age_s``: how old the report
        is, taken off the time it gave to the next fetch."""
        fetch = head.get("fetch") or {}
        with a.div(klass="card"):
            a.div(klass="label", _t="Panel")
            with a.div(klass="kv"):
                page = os.path.basename(fetch.get("next_url") or "")
                left = fetch.get("next_in_s", 0) - age_s
                kv(a, "next page", Markup("{}, {}").format(page, in_span(left)) if page else "—",
                   id=f"{k}-next-page")
                kv(a, "fetched", f"{fetch.get('ok', 0)} ok, {fetch.get('failed', 0)} failed",
                   id=f"{k}-fetches")
                step = fetch.get("backoff_step", 0)
                kv(a, "back-off", f"step {step}" if step else "none")
                temp = head.get("panel_temp_c")
                kv(a, "temperature", f"{temp} °C" if temp is not None else "—", id=f"{k}-panel-temp")

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
                if key == "psram" and not size:
                    continue
                specs.append({"kind": "meter", "canvas": f"#{k}-{key}-meter",
                              "fraction": free / size if size else 0.0})
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
# in; the queue is empty unless the server was away.
TRACES = (
    Trace("heap", "free memory, KB", free_memory_kb, y=(0, 320), step=100),
    Trace("queue", "queue, readings", queued),
)

# Which board is the dark line when both are on a chart: the dock, which is
# the only one on the queue chart.
TRACE_ORDER = ("canary-dock", "canary-head")


class DiagnosticsTracePage(EnvPage):
    """Both boards' free memory, and the dock's queue, over the last day,
    with each board's restarts."""
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
                n, faults = restarts(history.get(device, []))
                with a.div(klass="stat", id=f"{k}-stat"):
                    a.span(klass="name", _t=k)
                    line = (f"up {fmt_duration(c.get('uptime_s', 0))}, "
                            + (f"{n} restart{'s' if n != 1 else ''} today" if n else "no restarts today"))
                    if faults:
                        line = Markup('{}, <span class="fault">{}</span>').format(
                            line, f"{faults} fault{'s' if faults != 1 else ''}")
                    a.span(klass="detail", _t=line)
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


# The faults the health page counts: a count added up over the day, or a
# flag whose false spans are the fault. Each has its words for one and for
# many, and the verdict it gives when it leads. The first is the worst: a
# restart outranks any number of damaged answers.
HEALTH_TRACES = (
    ("restarts", ("restart", "restarts"), "A sensor restarted.",
     health_value("restarts"), True),
    ("pmsa003i", ("damaged PMSA003I frame", "damaged PMSA003I frames"), "PMSA003I dropping frames.",
     health_value("checksum_failures", "pmsa003i"), True),
    ("shtc3", ("SHTC3 checksum failure", "SHTC3 checksum failures"), "SHTC3 answers damaged.",
     health_value("checksum_failures", "shtc3"), True),
    ("scd41", ("SCD41 checksum failure", "SCD41 checksum failures"), "SCD41 answers damaged.",
     health_value("checksum_failures", "scd41"), True),
    ("heater", ("BME688 heater cold once", "BME688 heater cold {n} times"), "BME688 heater ran cold.",
     health_value("bme688", "heat_stable"), False),
)
# Faults in one quarter hour stack outward from the dial; past six the dots
# stop, and the number above the dial still counts them all.
SLOT_S = 15 * 60
MAX_STACK = 6


def rises(pts: list[list[int]]) -> list[list[int]]:
    """Each time a count went up, with how far it went up."""
    return [[after_ts, after - before]
            for (_, before), (after_ts, after) in zip(pts, pts[1:]) if after > before]


def false_spans(pts: list[list[int]], until: int) -> list[list[int]]:
    """The spans a flag read false over, each running to the next report."""
    out: list[list[int]] = []
    for i, (ts, value) in enumerate(pts):
        if value:
            continue
        end = pts[i + 1][0] if i + 1 < len(pts) else until
        if out and out[-1][1] == ts:
            out[-1][1] = end
        else:
            out.append([ts, end])
    return out


def day_fraction(ts: int, tz) -> float:
    """Where a time falls on a 24-hour clock face: 0 at midnight, 0.5 at noon."""
    t = datetime.fromtimestamp(ts, tz)
    return (t.hour * 3600 + t.minute * 60 + t.second) / 86400


def arcs(spans: list[list[int]], tz) -> list[list[float]]:
    """Spans of time as arcs of the clock face, cut at midnight."""
    out: list[list[float]] = []
    for t0, t1 in spans:
        if t1 - t0 >= 86400:
            return [[0.0, 1.0]]
        f0, f1 = day_fraction(t0, tz), day_fraction(t1, tz)
        out.extend([[f0, f1]] if f0 <= f1 else [[f0, 1.0], [0.0, f1]])
    return out


def covered_spans(pts: list[list[int]], gap: int) -> list[list[int]]:
    """The spans reports arrived over, cut wherever more than ``gap`` passed
    between two of them."""
    out: list[list[int]] = []
    for ts, _ in pts:
        if out and ts - out[-1][1] <= gap:
            out[-1][1] = ts
        else:
            out.append([ts, ts])
    return out


HEALTH_DEVICE = "canary-dock"


class HealthTracePage(EnvPage):
    """How the dock's sensors fared over the last day, as the other pages
    say a measurement: a number, a verdict and one drawing. The number counts
    the faults, and the drawing puts each on a 24-hour clock face. Below, what
    each sensor reports of its own settings."""
    title = "Sensor health"
    stylesheet = "health.css"
    css_class = "health-trace"
    requires = ("status", "status_history_24h")
    HOURS = 24
    # Reports arrive every ten minutes, so a longer silence is a gap in the
    # record rather than the next report running late.
    GAP_S = 20 * 60

    def _dock(self, status: dict | None, history: dict) -> tuple[dict | None, list[dict]]:
        """The dock's newest health object and its reports of the day that carry one."""
        entry = ((status or {}).get("boards") or {}).get(HEALTH_DEVICE) or {}
        newest = (entry.get("doc") or {}).get("health")
        reports = [d for d in history.get(HEALTH_DEVICE, []) if isinstance(d.get("health"), dict)]
        return (newest if isinstance(newest, dict) else None), reports

    def body(self, a: Airium, **data) -> None:
        status: dict | None = data["status"]
        newest, reports = self._dock(status, data["status_history_24h"] or {})
        a.div(klass="title label", _t="Sensor health")
        if status is None:
            a.div(klass="verdict", _t="No report from either board yet.")
            a.div(klass="detail", _t="Each posts once it connects.")
            return
        if newest is None:
            a.div(klass="verdict", _t="No health report from the dock yet.")
            a.div(klass="detail", _t="The dock sends one with every reading.")
            return
        doc = status["boards"][HEALTH_DEVICE]["doc"]
        end = doc["ts"]
        start = end - self.HOURS * 3600
        tallies = self._tallies(reports, start, end)
        total = sum(t["n"] for t in tallies)

        a.div(klass="stamp", _t=fmt_stamp(end, self.tz))
        a.div(klass="span", _t=f"last {self.HOURS} hours")
        with a.div(klass="hero", id="faults"):
            a.span(klass="value", _t=fmt_int(total))
            a.span(klass="unit", _t="fault" if total == 1 else "faults")
        worst = next((t for t in tallies if t["key"] == "restarts" and t["n"]), None) or \
            max(tallies, key=lambda t: t["n"])
        a.div(klass="verdict", _t=worst["verdict"] if total else "All sensors well.")

        said = [t["words"] for t in tallies if t["n"]]
        detail = [(", ".join(said) + ".") if said else "No faults."]
        first = min((c[0] for t in tallies for c in t["covered"]), default=None)
        if first is not None and first - start > self.GAP_S:
            detail.append(f"No reports before {fmt_hm(first, self.tz)}.")
        a.div(klass="detail", _t=" ".join(detail))

        with a.div(klass="dial"):
            a.canvas(id="health-dial")
        a.div(klass="caption", _t="the last 24 hours: "
                                  "large dots restarts, small dots damaged answers")
        self._settings(a, newest, ((doc.get("client") or {}).get("dock") or {}).get("bsec") or {})

    @staticmethod
    def _settings(a: Airium, health: dict, bsec: dict) -> None:
        """What each sensor reports of its own settings, a row each. A sensor
        that has not reported them yet says so rather than dropping out."""
        scd41 = health.get("scd41") or {}
        bme = health.get("bme688") or {}
        pm = health.get("pmsa003i") or {}
        shtc3 = health.get("shtc3") or {}
        rows = {"SCD41": [], "BME688": [], "PMSA003I": [], "SHTC3": []}
        if scd41.get("serial"):
            rows["SCD41"].append(f"serial {scd41['serial']}")
        if "asc" in scd41:
            rows["SCD41"].append("self-calibration " + ("on" if scd41["asc"] else "off"))
        if "offset_c" in scd41:
            rows["SCD41"].append(f"offset {scd41['offset_c']:.1f} °C")
        if "pressure_hpa" in scd41:
            rows["SCD41"].append(f"pressure {fmt_int(scd41['pressure_hpa'])} hPa")
        if "heater_c" in bme and "heater_ms" in bme:
            rows["BME688"].append(f"heater {bme['heater_c']} °C for {bme['heater_ms']} ms")
        if "restored" in bsec:
            rows["BME688"].append("BSEC state " + ("restored" if bsec["restored"] else "new"))
        if "version" in pm:
            rows["PMSA003I"].append(f"version {pm['version']}")
        if "error" in pm:
            rows["PMSA003I"].append("no error" if not pm["error"] else f"error {pm['error']}")
        if shtc3.get("id"):
            rows["SHTC3"].append(f"ID {shtc3['id']}")
        if "low_power" in shtc3:
            rows["SHTC3"].append("low-power mode" if shtc3["low_power"] else "normal mode")
        with a.div(klass="settings", id="settings"):
            a.div(klass="label", _t="Sensor settings")
            with a.div(klass="rows"):
                for name, parts in rows.items():
                    a.span(klass="name", _t=name)
                    a.span(klass="v", _t=" · ".join(parts) if parts else "not reported yet")

    def charts(self, **data) -> list[dict]:
        status: dict | None = data["status"]
        newest, reports = self._dock(status, data["status_history_24h"] or {})
        if newest is None:
            return []
        end = status["boards"][HEALTH_DEVICE]["doc"]["ts"]
        start = end - self.HOURS * 3600
        tallies = self._tallies(reports, start, end)
        return [{
            "kind": "dial", "canvas": "#health-dial",
            "covered": arcs(tallies[0]["covered"], self.tz),
            "bands": arcs([b for t in tallies for b in t["bands"]], self.tz),
            "dots": self._dots(tallies),
            "now": day_fraction(end, self.tz),
            "ticks": [{"f": h / 24, "label": f"{h:02d}"} for h in (0, 6, 12, 18)],
        }]

    def _dots(self, tallies: list[dict]) -> list[dict]:
        """A dot for each counted fault, at the middle of its quarter hour,
        and ``k`` for how many already sit there."""
        stacks: dict[int, int] = {}
        dots = []
        for t in tallies:
            for ts, n in t["events"]:
                slot = ts // SLOT_S
                for _ in range(n):
                    k = stacks.get(slot, 0)
                    if k >= MAX_STACK:
                        break
                    stacks[slot] = k + 1
                    dots.append({"f": day_fraction(slot * SLOT_S + SLOT_S // 2, self.tz),
                                 "k": k, "big": t["key"] == "restarts"})
        return dots

    def _tallies(self, reports: list[dict], start: int, end: int) -> list[dict]:
        """Each fault's count over the window and the words for it: for a
        count, where it rose and how far; for a flag, the spans it read false."""
        out = []
        for key, (one, many), verdict, value, counted in HEALTH_TRACES:
            pts = health_points(reports, value, start)
            t = {"key": key, "verdict": verdict, "events": [], "bands": [],
                 "covered": covered_spans(pts, self.GAP_S)}
            if counted:
                pts = since_start(pts)
                t["events"] = rises(pts)
                t["n"] = pts[-1][1] if pts else 0
            else:
                t["bands"] = false_spans(pts, end)
                t["n"] = len(t["bands"])
            if key == "heater":
                t["words"] = one if t["n"] == 1 else many.format(n=t["n"])
            else:
                t["words"] = f"{fmt_int(t['n'])} {one if t['n'] == 1 else many}"
            out.append(t)
        return out
