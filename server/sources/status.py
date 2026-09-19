"""What each board says about itself, kept the way readings are kept.

Both boards POST to ``/readings``: the dock sends measurements with a
``client`` object beside them, the head sends the ``client`` object alone.
That object is the board's own state — network, memory, panel, fetch counts
— so it goes to a store of its own, keyed by board and timestamp, and the
newest from each board is held in memory for the pages.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Mapping

from epd_server import ReadingsStore
from epd_server.source import DataSource, Fetcher

log = logging.getLogger("readings")


def status_doc(doc: dict) -> dict | None:
    """The board-describing part of a posted document, or None when it says
    nothing about the board."""
    client = doc.get("client")
    if not isinstance(client, dict) or not client:
        return None
    return {"ts": doc["ts"], "device": str(doc.get("device", "")), "client": client}


class DeviceReports:
    """The newest report from each board, and every report in ``store``.

    A board that held a document while the server was down sends it late, so
    "newest" is by the board's own ``ts``, not by when it arrived.
    """

    def __init__(self, now: Callable[[], float] = time.time,
                 store: ReadingsStore | None = None, keep_days: float = 0):
        self.now = now
        self.store = store
        self.keep_days = keep_days
        self.by_device: dict[str, dict] = {}     # device -> {"doc", "received"}
        self.count = 0

    @property
    def latest(self) -> dict | None:
        """The newest report of any board."""
        newest = self._newest()
        return newest["doc"] if newest else None

    @property
    def received(self) -> float | None:
        """When the newest report arrived."""
        newest = self._newest()
        return newest["received"] if newest else None

    def _newest(self) -> dict | None:
        if not self.by_device:
            return None
        return max(self.by_device.values(), key=lambda e: e["doc"]["ts"])

    def device(self, name: str) -> dict | None:
        """The newest report from one board: ``{"doc", "age_s"}``."""
        entry = self.by_device.get(name)
        if entry is None:
            return None
        return {"doc": entry["doc"], "age_s": max(0, int(self.now() - entry["received"]))}

    def devices(self) -> list[str]:
        """Every board that has reported, newest first."""
        return [d for d, _ in sorted(self.by_device.items(),
                                     key=lambda kv: kv[1]["doc"]["ts"], reverse=True)]

    def accept(self, doc: dict) -> None:
        ts = doc.get("ts")
        if isinstance(ts, bool) or not isinstance(ts, int):
            raise ValueError("ts must be an integer epoch")
        self.count += 1
        device = str(doc.get("device", ""))
        self._keep(doc)

        entry = self.by_device.get(device)
        if entry is not None and ts < entry["doc"]["ts"]:
            log.info("report %d from %s: a held reading from %d", self.count, device or "?", ts)
            return
        self.by_device[device] = {"doc": doc, "received": self.now()}
        client = doc.get("client") or {}
        log.info("report %d from %s at %s", self.count, device or "?", client.get("ip", "?"))

    def _keep(self, doc: dict) -> None:
        """Put the board's own state in the store, and drop what is too old."""
        if self.store is None:
            return
        block = status_doc(doc)
        if block is None:
            return
        self.store.add(block)
        if self.keep_days:
            self.store.prune(int(self.now() - self.keep_days * 86400))


class StatusSource(DataSource):
    """Dataset ``status``: ``{"doc", "age_s", "count"}`` for the newest report
    of any board, with ``boards`` naming what each board last said. None
    before the first report."""

    def __init__(self, reports: DeviceReports):
        self.reports = reports

    def status(self) -> dict | None:
        r = self.reports
        if r.latest is None or r.received is None:
            return None
        return {"doc": r.latest, "age_s": max(0, int(r.now() - r.received)), "count": r.count,
                "boards": {d: r.device(d) for d in r.devices()}}

    def history(self, hours: int) -> dict[str, list[dict]]:
        """Each board's reports of the last ``hours``, oldest first, by board."""
        store = self.reports.store
        if store is None:
            return {}
        out: dict[str, list[dict]] = {}
        for doc in store.between(int(self.reports.now()) - hours * 3600):
            out.setdefault(str(doc.get("device", "")), []).append(doc)
        return out

    def datasets(self) -> Mapping[str, Fetcher]:
        return {"status": self.status, "status_history_24h": lambda: self.history(24)}
