"""Sensor calibration the board sends, kept so it can have it back.

The dock posts ``{"device": ..., "calibration": {...}}`` to /calibration
whenever BSEC saves a new copy; the block is keyed by sensor.
Only the BME688 has learned state the board can back up: BSEC's, as base64,
with the IAQ accuracy, the time the copy was taken and the seconds between
BSEC's samples, since a copy learned at one rate is no use at another. This
keeps every copy for ``keep_days``, and answers the board's
``GET /calibration?device=&before=&sample_s=`` with the newest copy at that
rate saved before that time, preferring one that reached accuracy 3. The
board asks with its boot time, so it never gets back a copy it made since.

It also keeps the recalibrations asked of a board, each with the time it
was asked as its id, until a newer one takes its place.
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
    " sample_s INTEGER NOT NULL DEFAULT 3,"
    " PRIMARY KEY (device, sensor, saved))",
    "CREATE TABLE IF NOT EXISTS requests ("
    " id INTEGER PRIMARY KEY,"
    " device TEXT NOT NULL,"
    " sensor TEXT NOT NULL,"
    " ppm INTEGER NOT NULL)",
)

# The sensors whose state the board sends, the highest accuracy BSEC reports,
# and BSEC's two rates, in seconds between samples.
SENSORS = ("bme688",)
MAX_ACCURACY = 3
SAMPLE_S = (3, 300)


def _copy(entry) -> tuple[str, int, int, int] | None:
    """``(state, accuracy, saved, sample_s)`` from one sensor's entry, or None
    when it is not a usable copy. One saved before the board's clock was set
    has no age to weigh against another, so it is not kept."""
    if not isinstance(entry, dict):
        return None
    state, accuracy, saved = entry.get("state"), entry.get("accuracy"), entry.get("saved")
    rate = entry.get("sample_s")
    if not isinstance(state, str) or not state:
        return None
    if isinstance(accuracy, bool) or not isinstance(accuracy, int) or not 0 <= accuracy <= MAX_ACCURACY:
        return None
    if isinstance(saved, bool) or not isinstance(saved, int) or saved <= 0:
        return None
    if isinstance(rate, bool) or rate not in SAMPLE_S:
        return None
    return state, accuracy, saved, rate


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
            columns = {row[1] for row in self._db.execute("PRAGMA table_info(calibration)")}
            if "sample_s" not in columns:
                # Every copy kept before BSEC had a choice of rate was at 3 s.
                self._db.execute("ALTER TABLE calibration"
                                 " ADD COLUMN sample_s INTEGER NOT NULL DEFAULT 3")

    def add(self, device: str, block: Mapping) -> int:
        """Keep each usable copy in ``block``, and delete those older than
        ``keep_days``. Returns how many were kept. A copy the board sends
        again, the same sensor and time, is kept once."""
        rows = []
        for sensor in SENSORS:
            copy = _copy(block.get(sensor))
            if copy is not None:
                state, accuracy, saved, rate = copy
                rows.append((device, sensor, saved, accuracy, state, rate))
        with self._lock, self._db:
            self._db.executemany(
                "INSERT OR REPLACE INTO calibration"
                " (device, sensor, saved, accuracy, state, sample_s) VALUES (?, ?, ?, ?, ?, ?)",
                rows)
            if self.keep_days:
                self._db.execute("DELETE FROM calibration WHERE saved < ?",
                                 (int(self.now() - self.keep_days * 86400),))
        return len(rows)

    def lookup(self, device: str, before: int, sample_s: int) -> dict | None:
        """Each sensor's newest copy at ``sample_s`` saved before ``before``,
        one at accuracy 3 first, in the shape of the block the board sends.
        None when there is none."""
        answer = {}
        with self._lock:
            for sensor in SENSORS:
                row = self._db.execute(
                    "SELECT state, accuracy, saved FROM calibration"
                    " WHERE device = ? AND sensor = ? AND saved < ? AND sample_s = ?"
                    " ORDER BY accuracy >= ? DESC, saved DESC LIMIT 1",
                    (device, sensor, before, sample_s, MAX_ACCURACY)).fetchone()
                if row:
                    answer[sensor] = {"state": row[0], "accuracy": row[1], "saved": row[2],
                                      "sample_s": sample_s}
        return answer or None

    def accept(self, docs: list[dict]) -> None:
        """The POST /calibration handler: each document's block, for its device.

        Raises:
            ValueError: a document has no ``device`` string or no
                ``calibration`` object; nothing is kept.
        """
        for doc in docs:
            if not isinstance(doc.get("device"), str) or not doc["device"]:
                raise ValueError("device is required")
            if not isinstance(doc.get("calibration"), dict):
                raise ValueError("calibration must be an object")
        for doc in docs:
            self.add(doc["device"], doc["calibration"])

    def answer(self, args: Mapping[str, str]) -> dict | None:
        """The GET /calibration handler, with ``device``, ``before`` and
        ``sample_s`` from the query string."""
        device = args.get("device")
        if not device:
            raise ValueError("device is required")
        try:
            before = int(args.get("before", ""))
        except ValueError:
            raise ValueError("before must be an integer epoch") from None
        try:
            rate = int(args.get("sample_s", ""))
        except ValueError:
            rate = 0
        if rate not in SAMPLE_S:
            raise ValueError(f"sample_s must be one of {', '.join(map(str, SAMPLE_S))}")
        return self.lookup(device, before, rate)

    def request(self, device: str, sensor: str, ppm: int, at: int) -> int:
        """Ask ``device`` to recalibrate ``sensor`` to ``ppm``. Returns the
        request's id: ``at``, or one past the last id when that is later."""
        with self._lock, self._db:
            last = self._db.execute("SELECT MAX(id) FROM requests").fetchone()[0] or 0
            request_id = max(at, last + 1)
            self._db.execute("DELETE FROM requests WHERE device = ? AND sensor = ?",
                             (device, sensor))
            self._db.execute("INSERT INTO requests (id, device, sensor, ppm) VALUES (?, ?, ?, ?)",
                             (request_id, device, sensor, ppm))
        return request_id

    def pending(self, device: str, done_id: int, since: float) -> dict | None:
        """The newest request of ``device`` past ``done_id`` and asked after
        ``since``, as ``{"id", "ppm"}``, or None."""
        with self._lock:
            row = self._db.execute(
                "SELECT id, ppm FROM requests WHERE device = ? AND id > ? AND id > ?"
                " ORDER BY id DESC LIMIT 1", (device, done_id, since)).fetchone()
        return {"id": row[0], "ppm": row[1]} if row else None

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM calibration").fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self._db.close()
