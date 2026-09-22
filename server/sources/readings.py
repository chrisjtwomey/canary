"""Every readings document the board posts, kept for the pages.

The dock queues a document for each reading and posts the queue to
/sensor-readings, up to a hundred at a time. The whole document goes to
DeviceReports, for the Diagnostics pages; the store gets the measurements
only. The client and health objects are the board's own state, and a
calibration block is sensor state, not a reading of the room: the dock
sends that to /calibration.
"""
from __future__ import annotations

import time
from typing import Callable

from epd_server import ReadingsStore
from epd_server.store import key

from sources.status import DeviceReports

# Keys of a posted document that describe the board, not the room.
BOARD_KEYS = ("client", "health", "calibration")
# The most documents one GET /sensor-readings answers with.
MAX_READINGS = 5000


def measurements(doc: dict) -> dict:
    """``doc`` without the keys that describe the board."""
    return {k: v for k, v in doc.items() if k not in BOARD_KEYS}


def has_measurements(doc: dict) -> bool:
    """Whether ``doc`` says anything about the room. The head posts its own
    state and no readings, and that is not a reading of anything."""
    return any(k not in ("ts", "device") for k in measurements(doc))


class ReadingsIngest:
    """The /sensor-readings handler: each report for Diagnostics, every reading
    into the readings store, and readings older than ``keep_days`` deleted.
    Without a readings store it keeps the reports only."""

    def __init__(self, reports: DeviceReports, store: ReadingsStore | None = None,
                 keep_days: float = 0, now: Callable[[], float] = time.time):
        self.reports = reports
        self.store = store
        self.keep_days = keep_days
        self.now = now

    def accept(self, docs: list[dict]) -> dict:
        """Take a batch, and answer ``{"new": n, "repeated": m}``.

        Posting a document again stores it once. Each store keys a document
        by its ``device`` and ``ts``, and ignores a second one with the same
        pair, so a board that lost the reply to a POST can send the same
        documents again, alone or in another batch, and change nothing.
        ``repeated`` counts those.

        Raises:
            ValueError: a document has no integer ``ts`` or a ``device``
                that is not a string; nothing is taken.
        """
        for doc in docs:
            key(doc)
        fresh = self.reports.accept_many(docs)
        readings = [(i, measurements(doc)) for i, doc in enumerate(docs) if has_measurements(doc)]
        if self.store is not None and readings:
            for (i, _), new in zip(readings, self.store.add_many([m for _, m in readings])):
                fresh[i] = new
            if self.keep_days:
                self.store.prune(int(self.now() - self.keep_days * 86400))
        new = sum(fresh)
        return {"new": new, "repeated": len(docs) - new}


def epoch_arg(args: dict, name: str, default: int) -> int:
    """The query argument ``name`` as epoch seconds, or ``default`` when it is absent.

    Raises:
        ValueError: the argument is not a whole number.
    """
    value = args.get(name)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{name} must be epoch seconds") from None


class ReadingsQuery:
    """The GET side of /sensor-readings: the stored documents between two times, as
    the boards posted them, for a person or a script diagnosing a board.

    Args:
        between: the documents from one epoch to another, oldest first.
    """

    def __init__(self, between: Callable[[int, int], list[dict]],
                 now: Callable[[], float] = time.time):
        self.between = between
        self.now = now

    def answer(self, args: dict) -> dict:
        """The documents from ``from`` to ``to``, epoch seconds, the last day
        by default, of the board ``device`` when it is given. At most
        MAX_READINGS, the newest; ``left_out`` counts the older ones.

        Raises:
            ValueError: a time that is not a number, or a window that ends
                before it starts.
        """
        end = epoch_arg(args, "to", int(self.now()))
        start = epoch_arg(args, "from", end - 86400)
        if end < start:
            raise ValueError("the window must end after it starts")
        docs = self.between(start, end)
        device = args.get("device")
        if device:
            docs = [d for d in docs if d.get("device") == device]
        kept = docs[-MAX_READINGS:]
        return {"from": start, "to": end, "count": len(kept),
                "left_out": len(docs) - len(kept), "readings": kept}
