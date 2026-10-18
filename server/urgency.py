"""The display's page for each wake while a measurement needs attention.

A measurement is urgent when it is at or over its alert threshold, or
changing fast as its delta page judges a change, in that order of urgency.
Temperature and humidity have no alert threshold: outside the comfort
settings' acceptable range counts as over. Close to a threshold is not
urgent: a room is close for much of the day, and the pages' guide lines
show it. While any measurement is urgent, the display shows its pages in
turn in place of the schedule's: the main page first for a threshold, the
delta page first for a fast change, then the other, then the trace. Urgent measurements take turns, most urgent first, and one page
of the schedule's own follows each full turn. Only pages in the display's
pools show. The wake times never change.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from dock_settings import DockSettings
from metrics import IAQ_CALIBRATED_ACCURACY, Comfort, change_over, classify_rate
from pages.pool import CO2, IAQ, PM25, PRESSURE, Metric, comfort_metrics

log = logging.getLogger("urgency")

OVER, FAST = 2, 1
LEVEL_WORDS = {OVER: "over its alert threshold", FAST: "changing fast"}


@dataclass(frozen=True)
class Measurement:
    """A measurement and its pages. ``metrics`` are the values whose change
    counts; the first is the one its delta page shows."""
    name: str
    metrics: tuple[Metric, ...]
    main: str
    delta: str
    trace: str


@dataclass(frozen=True)
class Urgent:
    measurement: Measurement
    level: int
    delta_first: bool

    def pages(self, shown: set[str]) -> list[str]:
        m = self.measurement
        order = (m.delta, m.main, m.trace) if self.delta_first else (m.main, m.delta, m.trace)
        return [p for p in order if p and p in shown]


def measurements(comfort: Comfort) -> tuple[Measurement, ...]:
    temp, rh = comfort_metrics(comfort)
    return (
        Measurement("co2", (CO2,), "breathe.png", "co2-delta.png", "co2-trace.png"),
        Measurement("comfort", (temp, rh), "comfort.png", "comfort-delta.png", "comfort-trace.png"),
        Measurement("dust", (PM25,), "dust.png", "dust-delta.png", "dust-trace.png"),
        Measurement("air", (IAQ,), "air.png", "air-delta.png", "air-trace.png"),
        Measurement("barometer", (PRESSURE,), "", "barometer-delta.png", "barometer-trace.png"),
    )


def _valid(latest: dict, m: Metric) -> bool:
    return bool(latest.get("valid", {}).get(m.valid_flag)) and latest.get(m.key) is not None


def over(name: str, latest: dict, alerts: DockSettings, comfort: Comfort) -> bool:
    """Whether the measurement ``name`` in ``latest`` is at or over its limit."""
    if name == "co2" and _valid(latest, CO2):
        return latest[CO2.key] >= alerts.scd41_poor_air_ppm
    if name == "dust" and _valid(latest, PM25):
        return latest[PM25.key] >= alerts.pm_poor_air_ug_m3
    if name == "air" and _valid(latest, IAQ) \
            and (latest.get(IAQ.accuracy_key) or 0) >= IAQ_CALIBRATED_ACCURACY:
        return latest[IAQ.key] >= alerts.bsec_poor_air_iaq
    if name == "comfort":
        temp, rh = comfort_metrics(comfort)
        t = latest.get(temp.key) if _valid(latest, temp) else None
        h = latest.get(rh.key) if _valid(latest, rh) else None
        bands = ([comfort.temp_band(t, h)] if t is not None else []) + \
                ([comfort.rh_band(h, t)] if h is not None else [])
        return any(b in ("cold", "hot", "very dry", "very humid") for b in bands)
    return False


def _fast(m: Metric, latest: dict, history: list[dict]) -> bool:
    if not _valid(latest, m):
        return False
    rate = classify_rate(change_over(history, latest, m.key, m.window_h), m.slow, m.fast)
    return rate in ("rising fast", "falling fast")


def urgent(latest: dict, history: list[dict], alerts: DockSettings,
           comfort: Comfort) -> list[Urgent]:
    """Each urgent measurement in ``latest``, most urgent first."""
    if not latest or "ts" not in latest:
        return []
    found = []
    for m in measurements(comfort):
        limit = over(m.name, latest, alerts, comfort)
        fast = [_fast(metric, latest, history) for metric in m.metrics]
        if limit or any(fast):
            found.append(Urgent(m, OVER if limit else FAST, delta_first=not limit and fast[0]))
    return sorted(found, key=lambda u: -u.level)


class Prioritiser:
    """DisplayServer's ``choose_page``: the next page of the urgent
    measurements' turn, or the scheduled page.

    Args:
        fetch: the newest reading and the last day's, fresh at each call.
        shown: the pages in the display's pools.
        keep: pages never replaced, such as the splash while the schedule is off.
    """

    def __init__(self, fetch: Callable[[], tuple[dict, list[dict]]], shown: set[str],
                 alerts: DockSettings, comfort: Comfort, keep: set[str] = frozenset()):
        self.fetch = fetch
        self.shown = shown
        self.alerts = alerts
        self.comfort = comfort
        self.keep = keep
        self.turn: tuple = ()
        self.step = 0

    def choose(self, scheduled: str, wake: datetime) -> str:
        if scheduled in self.keep:
            return scheduled
        latest, history = self.fetch()
        found = [u for u in urgent(latest, history, self.alerts, self.comfort) if u.pages(self.shown)]
        turn = tuple((u.measurement.name, u.level, u.delta_first) for u in found)
        if turn != self.turn:
            self.turn, self.step = turn, 0
            log.info("urgent: %s", ", ".join(f"{u.measurement.name} {LEVEL_WORDS[u.level]}"
                                             for u in found) or "nothing")
        if not found:
            return scheduled
        lists = [u.pages(self.shown) for u in found]
        cycle = []
        for i in range(max(map(len, lists))):
            cycle += [pages[i] for pages in lists if i < len(pages)]
        cycle.append(scheduled)
        page = cycle[self.step % len(cycle)]
        self.step += 1
        return page
