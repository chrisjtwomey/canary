"""Every readings document the board posts, kept for the pages.

The board posts one document a minute to /readings. The whole document
goes to DeviceReports, for the Diagnostics page; the store gets the
measurements only. The client object is the board's own state, which only
the newest report needs, and a calibration block is sensor state, not a
reading of the room.
"""
from __future__ import annotations

import time
from typing import Callable

from epd_server import ReadingsStore

from sources.status import DeviceReports

# Keys of a posted document that describe the board, not the room.
BOARD_KEYS = ("client", "calibration")


def measurements(doc: dict) -> dict:
    """``doc`` without the keys that describe the board."""
    return {k: v for k, v in doc.items() if k not in BOARD_KEYS}


class ReadingsIngest:
    """The /readings handler: the newest report for Diagnostics, every
    reading into the store, and readings older than ``keep_days`` deleted.
    Without a store it only keeps the newest report."""

    def __init__(self, reports: DeviceReports, store: ReadingsStore | None = None,
                 keep_days: float = 0, now: Callable[[], float] = time.time):
        self.reports = reports
        self.store = store
        self.keep_days = keep_days
        self.now = now

    def accept(self, doc: dict) -> None:
        self.reports.accept(doc)
        if self.store is None:
            return
        self.store.add(measurements(doc))
        if self.keep_days:
            self.store.prune(int(self.now() - self.keep_days * 86400))
