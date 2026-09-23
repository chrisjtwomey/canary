"""What each board says about itself, kept the way readings are kept.

Both boards POST to ``/sensor-readings``: the dock sends measurements with a
``client`` object and a ``health`` object beside them, the head sends the
``client`` object alone. Those are the board's own state — network, memory,
panel, fetch counts, how its sensors fare — so they go to a store of their
own, keyed by board and timestamp, and the newest from each board is held in
memory for the pages.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Mapping

from epd_server import ReadingsStore
from epd_server.compat import version_order
from epd_server.source import DataSource, Fetcher

log = logging.getLogger("readings")


def status_doc(doc: dict) -> dict | None:
    """The board-describing part of a posted document, or None when it says
    nothing about the board."""
    client = doc.get("client")
    if not isinstance(client, dict) or not client:
        return None
    kept = {"ts": doc["ts"], "device": str(doc.get("device", "")), "client": client}
    if isinstance(doc.get("health"), dict):
        kept["health"] = doc["health"]
    return kept


class DeviceReports:
    """The newest report from each board, and every report in ``store``.

    A board that held a document while the server was down sends it late, so
    "newest" is by the board's own ``ts``, not by when it arrived. Beside it,
    held in memory: the last time each board's version changed, and the posts
    the server refused because of a board's version.
    """

    def __init__(self, now: Callable[[], float] = time.time,
                 store: ReadingsStore | None = None, keep_days: float = 0):
        self.now = now
        self.store = store
        self.keep_days = keep_days
        self.by_device: dict[str, dict] = {}     # device -> {"doc", "received"}
        self.changes: dict[str, dict] = {}       # device -> {"from", "to", "at", "older"}
        self.refusals: dict[str, dict] = {}      # device -> {"version", "count", "at"}
        self.count = 0
        if store is not None:
            self._restore()

    def _restore(self) -> None:
        """Take each board's newest report back from the store, so a restart
        does not blank the pages until every board posts again. A restored
        report's own ``ts`` stands in for when it arrived."""
        if self.keep_days:
            self.store.prune(int(self.now() - self.keep_days * 86400))
        for doc in self.store.latest_each():
            self.by_device[str(doc.get("device", ""))] = {"doc": doc, "received": doc["ts"]}
        self.count = self.store.count()

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
        """What is known of one board: ``{"doc", "age_s"}`` for its newest
        report, both None when the server has refused all it sent, and
        ``changed`` and ``refused`` when there is one to tell."""
        entry = self.by_device.get(name)
        refused = self.refusals.get(name)
        if entry is None and refused is None:
            return None
        out = {"doc": entry["doc"] if entry else None,
               "age_s": max(0, int(self.now() - entry["received"])) if entry else None}
        change = self.changes.get(name)
        if change is not None:
            out["changed"] = {**change, "age_s": max(0, int(self.now() - change["at"]))}
        if refused is not None:
            out["refused"] = {**refused, "age_s": max(0, int(self.now() - refused["at"]))}
        return out

    def devices(self) -> list[str]:
        """Every board that has reported, newest first, then any the server
        has only refused."""
        reported = [d for d, _ in sorted(self.by_device.items(),
                                         key=lambda kv: kv[1]["doc"]["ts"], reverse=True)]
        return reported + [d for d in self.refusals if d not in self.by_device]

    def refused(self, device: str, version: str) -> None:
        """The server turned a post away because of the board's version: the
        hook ``DisplayServer(on_refused=...)`` calls."""
        held = self.refusals.get(device)
        count = held["count"] + 1 if held and held["version"] == version else 1
        self.refusals[device] = {"version": version, "count": count, "at": self.now()}

    def accept(self, doc: dict) -> bool:
        """Take one report. False when the store already held it."""
        return self.accept_many([doc])[0]

    def accept_many(self, docs: list[dict]) -> list[bool]:
        """Take a batch of reports, and say which were new.

        ``count`` counts only new reports, so a board sending a report again
        after losing the reply does not inflate it. A report the store does
        not keep, one without a ``client`` object or with no store at all,
        counts as new.

        Raises:
            ValueError: a ``ts`` is not an integer; nothing is taken.
        """
        for doc in docs:
            ts = doc.get("ts")
            if isinstance(ts, bool) or not isinstance(ts, int):
                raise ValueError("ts must be an integer epoch")
        fresh = self._keep(docs)
        for doc, new in zip(docs, fresh):
            self._note(doc, new)
        return fresh

    def _note(self, doc: dict, new: bool) -> None:
        device = str(doc.get("device", ""))
        if not new:
            log.info("report from %s at %d: already held", device or "?", doc["ts"])
            return
        self.count += 1
        entry = self.by_device.get(device)
        if entry is not None and doc["ts"] < entry["doc"]["ts"]:
            log.info("report %d from %s: a held reading from %d", self.count, device or "?", doc["ts"])
            return
        client = doc.get("client") or {}
        self._version_seen(device, entry, client.get("version"))
        self.by_device[device] = {"doc": doc, "received": self.now()}
        log.info("report %d from %s at %s", self.count, device or "?", client.get("ip", "?"))

    def _version_seen(self, device: str, entry: dict | None, version) -> None:
        """Note a board now running another version, and forget a refusal
        its new version answers."""
        refused = self.refusals.get(device)
        if refused is not None and refused["version"] != version:
            del self.refusals[device]
        before = ((entry or {}).get("doc", {}).get("client") or {}).get("version")
        if not before or not version or before == version:
            return
        older = (version_order(version) or (0, 0, 0)) < (version_order(before) or (0, 0, 0))
        self.changes[device] = {"from": before, "to": version, "at": self.now(), "older": older}
        if older:
            log.warning("%s went back from %s to %s", device or "?", before, version)
        else:
            log.info("%s moved from %s to %s", device or "?", before, version)

    def _keep(self, docs: list[dict]) -> list[bool]:
        """Put each board's own state in the store, drop what is too old, and
        say which reports were new."""
        fresh = [True] * len(docs)
        if self.store is None:
            return fresh
        blocks = [(i, status_doc(doc)) for i, doc in enumerate(docs)]
        blocks = [(i, b) for i, b in blocks if b is not None]
        if not blocks:
            return fresh
        for (i, _), new in zip(blocks, self.store.add_many([b for _, b in blocks])):
            fresh[i] = new
        if self.keep_days:
            self.store.prune(int(self.now() - self.keep_days * 86400))
        return fresh


class StatusSource(DataSource):
    """Dataset ``status``: ``{"doc", "age_s", "count"}`` for the newest report
    of any board, with ``boards`` naming what each board last said. None
    before the first report or refusal; ``doc`` and ``age_s`` are None while
    the server has only refused posts."""

    def __init__(self, reports: DeviceReports):
        self.reports = reports

    def status(self) -> dict | None:
        r = self.reports
        if (r.latest is None or r.received is None) and not r.refusals:
            return None
        age = max(0, int(r.now() - r.received)) if r.received is not None else None
        return {"doc": r.latest, "age_s": age, "count": r.count,
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
