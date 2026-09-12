"""The last document the board posted, as a dataset for the pages.

The board POSTs one readings document a minute to ``/readings`` with a
``client`` object beside the measurements: its network, memory, panel and
fetch state. Until the readings store exists, only the newest is kept.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Mapping

from epd_server.source import DataSource, Fetcher

log = logging.getLogger("readings")


class DeviceReports:
    """Keeps the newest document POSTed to /readings: the one with the
    highest ``ts``, so a reading the board held while the server was down
    does not replace its live report when it arrives late."""

    def __init__(self, now: Callable[[], float] = time.time):
        self.now = now
        self.latest: dict | None = None
        self.received: float | None = None
        self.count = 0

    def accept(self, doc: dict) -> None:
        ts = doc.get("ts")
        if isinstance(ts, bool) or not isinstance(ts, int):
            raise ValueError("ts must be an integer epoch")
        self.count += 1
        if self.latest is not None and ts < self.latest["ts"]:
            log.info("report %d from %s: a held reading from %d", self.count,
                     doc.get("device", "?"), ts)
            return
        self.latest = doc
        self.received = self.now()
        client = doc.get("client") or {}
        log.info("report %d from %s at %s", self.count, doc.get("device", "?"), client.get("ip", "?"))


class StatusSource(DataSource):
    """Dataset ``status``: ``{"doc", "age_s", "count"}``, or None before the
    first report."""

    def __init__(self, reports: DeviceReports):
        self.reports = reports

    def status(self) -> dict | None:
        r = self.reports
        if r.latest is None or r.received is None:
            return None
        return {"doc": r.latest, "age_s": max(0, int(r.now() - r.received)), "count": r.count}

    def datasets(self) -> Mapping[str, Fetcher]:
        return {"status": self.status}
