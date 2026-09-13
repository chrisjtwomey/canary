"""Sensor calibration the board sends, kept so it can have it back.

Each live readings POST carries a ``calibration`` block keyed by sensor.
Only the BME688 has learned state the board can back up: BSEC's, as base64,
with the IAQ accuracy and the time the copy was taken. This keeps every
copy for ``keep_days``, and answers the board's
``GET /calibration?device=&before=`` with the newest copy saved before that
time, preferring one that reached accuracy 3. The board asks with its boot
time, so it never gets back a copy it made since.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from typing import Callable, Mapping

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS calibration ("
    " device TEXT NOT NULL,"
    " sensor TEXT NOT NULL,"
    " saved INTEGER NOT NULL,"
    " accuracy INTEGER NOT NULL,"
    " state TEXT NOT NULL,"
    " PRIMARY KEY (device, sensor, saved))",
)

# The sensors whose state the board sends, and the highest accuracy BSEC reports.
SENSORS = ("bme688",)
MAX_ACCURACY = 3


def _copy(entry) -> tuple[str, int, int] | None:
    """``(state, accuracy, saved)`` from one sensor's entry, or None when it
    is not a usable copy. One saved before the board's clock was set has no
    age to weigh against another, so it is not kept."""
    if not isinstance(entry, dict):
        return None
    state, accuracy, saved = entry.get("state"), entry.get("accuracy"), entry.get("saved")
    if not isinstance(state, str) or not state:
        return None
    if isinstance(accuracy, bool) or not isinstance(accuracy, int) or not 0 <= accuracy <= MAX_ACCURACY:
        return None
    if isinstance(saved, bool) or not isinstance(saved, int) or saved <= 0:
        return None
    return state, accuracy, saved


class CalibrationStore:
    """Every copy of each sensor's calibration, in one SQLite table."""

    def __init__(self, path: str | os.PathLike, keep_days: float = 3,
                 now: Callable[[], float] = time.time):
        self.path = os.fspath(path)
        self.keep_days = keep_days
        self.now = now
        # Shared by the HTTP thread that adds and the one that answers.
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        with self._lock, self._db:
            for statement in _SCHEMA:
                self._db.execute(statement)

    def add(self, device: str, block: Mapping) -> int:
        """Keep each usable copy in ``block``, and delete those older than
        ``keep_days``. Returns how many were kept. A copy the board sends
        again, the same sensor and time, is kept once."""
        rows = []
        for sensor in SENSORS:
            copy = _copy(block.get(sensor))
            if copy is not None:
                state, accuracy, saved = copy
                rows.append((device, sensor, saved, accuracy, state))
        with self._lock, self._db:
            self._db.executemany(
                "INSERT OR REPLACE INTO calibration (device, sensor, saved, accuracy, state)"
                " VALUES (?, ?, ?, ?, ?)", rows)
            if self.keep_days:
                self._db.execute("DELETE FROM calibration WHERE saved < ?",
                                 (int(self.now() - self.keep_days * 86400),))
        return len(rows)

    def lookup(self, device: str, before: int) -> dict | None:
        """Each sensor's newest copy saved before ``before``, one at accuracy 3
        first, in the shape of the block the board sends. None when there is
        none."""
        answer = {}
        with self._lock:
            for sensor in SENSORS:
                row = self._db.execute(
                    "SELECT state, accuracy, saved FROM calibration"
                    " WHERE device = ? AND sensor = ? AND saved < ?"
                    " ORDER BY accuracy >= ? DESC, saved DESC LIMIT 1",
                    (device, sensor, before, MAX_ACCURACY)).fetchone()
                if row:
                    answer[sensor] = {"state": row[0], "accuracy": row[1], "saved": row[2]}
        return answer or None

    def answer(self, args: Mapping[str, str]) -> dict | None:
        """The GET /calibration handler, with ``device`` and ``before`` from
        the query string."""
        device = args.get("device")
        if not device:
            raise ValueError("device is required")
        try:
            before = int(args.get("before", ""))
        except ValueError:
            raise ValueError("before must be an integer epoch") from None
        return self.lookup(device, before)

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM calibration").fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self._db.close()
