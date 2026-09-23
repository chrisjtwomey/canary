"""A store as a file, out and back in: one JSON document a line.

Each store keeps what a board sent, keyed by the board and a time. An export
is those documents in that form, so a file from one server goes into another
of the same kind. What the file and the store both hold is the question an
import has to ask: it writes the whole file or none of it, and it does not
put a document over one that is already there unless it is told to.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Iterator

from epd_server.logs import LEVELS
from epd_server.store import key

from sources.calibration import MAX_ACCURACY, SAMPLE_S, SENSORS

# Rows read, written or asked about in one go. Three key columns a row keeps
# the question about a batch under any SQLite's limit on how many values it takes.
ROWS_AT_A_TIME = 300
# How many lines the size of a download is measured from.
SAMPLE_ROWS = 500
# How long a write waits for the server's own connection to finish.
BUSY_SECONDS = 30


class Corrupt(Exception):
    """A line of the file is not a document this store can hold."""

    def __init__(self, line: int, why: str):
        super().__init__(f"line {line}: {why}")
        self.line = line
        self.why = why


class Overlap(Exception):
    """The file holds documents the store already has, and nothing said
    whether to put them over them."""

    def __init__(self, held: int, total: int):
        super().__init__(f"{held} of {total} are already held")
        self.held = held
        self.total = total


def _readings_row(doc: Any) -> tuple:
    if not isinstance(doc, dict):
        raise ValueError("not an object")
    device, ts = key(doc)
    return device, ts, json.dumps(doc, separators=(",", ":"))


def _calibration_row(doc: Any) -> tuple:
    if not isinstance(doc, dict):
        raise ValueError("not an object")
    device, sensor, state = doc.get("device"), doc.get("sensor"), doc.get("state")
    saved, accuracy = doc.get("saved"), doc.get("accuracy")
    if not isinstance(device, str) or not device:
        raise ValueError("device must be a string")
    if sensor not in SENSORS:
        raise ValueError("sensor must be one this server knows")
    if isinstance(saved, bool) or not isinstance(saved, int) or saved <= 0:
        raise ValueError("saved must be an epoch")
    if isinstance(accuracy, bool) or not isinstance(accuracy, int) \
            or not 0 <= accuracy <= MAX_ACCURACY:
        raise ValueError("accuracy must be 0 to 3")
    if not isinstance(state, str) or not state:
        raise ValueError("state must be a string")
    # A file exported before BSEC had a choice of rate holds 3 s copies.
    rate = doc.get("sample_s", SAMPLE_S[0])
    if isinstance(rate, bool) or rate not in SAMPLE_S:
        raise ValueError("sample_s must be 3 or 300")
    return device, sensor, saved, accuracy, state, rate


def _logs_row(doc: Any) -> tuple:
    if not isinstance(doc, dict):
        raise ValueError("not an object")
    board, received, level, text = doc.get("board"), doc.get("received"), doc.get("level"), doc.get("text")
    if not isinstance(board, str) or not board:
        raise ValueError("board must be a string")
    if isinstance(received, bool) or not isinstance(received, (int, float)) or received <= 0:
        raise ValueError("received must be an epoch")
    if level is not None and (isinstance(level, bool) or not isinstance(level, int)
                              or not 0 <= level < len(LEVELS)):
        raise ValueError("level must be empty or 0 to 5")
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    return board, received, level, text


@dataclass(frozen=True)
class Kind:
    """One store's table: what a line of its file holds, what makes two
    documents the same one, and how a document becomes a row."""
    table: str
    columns: tuple[str, ...]        # the columns a line is made from
    order: str                      # the column a download is sorted by
    keys: tuple[str, ...]           # the columns a document is kept under
    insert: tuple[str, ...]         # the columns a row is written to
    row: Callable[[Any], tuple]


KINDS = {
    "readings": Kind("readings", ("doc",), "ts", ("device", "ts"),
                     ("device", "ts", "doc"), _readings_row),
    "calibration": Kind("calibration", ("device", "sensor", "saved", "accuracy", "state", "sample_s"),
                        "saved", ("device", "sensor", "saved"),
                        ("device", "sensor", "saved", "accuracy", "state", "sample_s"),
                        _calibration_row),
    "logs": Kind("lines", ("board", "received", "level", "text"), "id",
                 ("board", "received", "text"), ("board", "received", "level", "text"), _logs_row),
}


class Transfer:
    """One store as a file to download, and the file back.

    Args:
        name: the URL and the file name stem, such as ``sensor-readings``.
        path: the SQLite file, which need not exist.
        kind: which table it holds, a key of :data:`KINDS`.
    """

    def __init__(self, name: str, path: str, kind: str = "readings"):
        self.name = name
        self.path = path
        self.kind = KINDS[kind]

    @property
    def table(self) -> str:
        return self.kind.table

    def size(self) -> int:
        """About how many bytes the download is: the length of the first
        :data:`SAMPLE_ROWS` lines, over how many documents are held. 0 when
        the store holds nothing or the file is not there yet.

        A sample, so the page costs the same to draw whether the store holds
        a day or a year.
        """
        db = self._open("ro")
        if db is None:
            return 0
        try:
            held = db.execute(f"SELECT COUNT(*) FROM {self.table}").fetchone()[0]
            if not held:
                return 0
            rows = db.execute(f"SELECT {self._columns} FROM {self.table}"
                              f" LIMIT {SAMPLE_ROWS}").fetchall()
            each = sum(len(self._line(row).encode()) for row in rows) / len(rows)
            return round(each * held)
        finally:
            db.close()

    def lines(self) -> Iterator[str]:
        """Each document as a line of JSON, oldest first."""
        db = self._open("ro")
        if db is None:
            return
        try:
            rows = db.execute(f"SELECT {self._columns} FROM {self.table}"
                              f" ORDER BY {self.kind.order}")
            while batch := rows.fetchmany(ROWS_AT_A_TIME):
                for row in batch:
                    yield self._line(row)
        finally:
            db.close()

    def take(self, lines: Iterable[bytes | str], overwrite: bool = False) -> dict:
        """Put a file's documents in the store, all of them or none.

        Returns ``{"added": n, "held": m, "total": t}``: how many the store
        did not have, how many it already had, and how many the file holds.

        Raises:
            Corrupt: a line is not a document this store can hold. Nothing
                is written, whichever line it is.
            Overlap: the store already holds some of them and ``overwrite``
                is false. Nothing is written.
            FileNotFoundError: this store is not one the server keeps.
        """
        db = self._open("rw")
        if db is None:
            raise FileNotFoundError(self.path)
        put = (f"INSERT OR {'REPLACE' if overwrite else 'IGNORE'} INTO {self.table}"
               f" ({', '.join(self.kind.insert)})"
               f" VALUES ({', '.join('?' * len(self.kind.insert))})")
        total = held = 0
        try:
            for rows in self._rows(lines):
                total += len(rows)
                held += self._already(db, rows)
                db.executemany(put, rows)
            if held and not overwrite:
                raise Overlap(held, total)
            db.commit()
            return {"added": total - held, "held": held, "total": total}
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _already(self, db: sqlite3.Connection, rows: list[tuple]) -> int:
        """How many of ``rows`` the store holds under their key already."""
        keys = self.kind.keys
        at = [self.kind.insert.index(k) for k in keys]
        values = ", ".join(f"({', '.join('?' * len(keys))})" for _ in rows)
        return db.execute(
            f"SELECT COUNT(*) FROM {self.table} WHERE ({', '.join(keys)}) IN (VALUES {values})",
            [row[i] for row in rows for i in at]).fetchone()[0]

    def _rows(self, lines: Iterable[bytes | str]) -> Iterator[list[tuple]]:
        """The file's documents as rows, a batch at a time."""
        batch: list[tuple] = []
        for number, line in enumerate(lines, 1):
            text = line.decode() if isinstance(line, bytes) else line
            if not text.strip():
                continue
            try:
                batch.append(self.kind.row(json.loads(text)))
            except (ValueError, UnicodeDecodeError) as exc:
                raise Corrupt(number, str(exc)) from None
            if len(batch) == ROWS_AT_A_TIME:
                yield batch
                batch = []
        if batch:
            yield batch

    @property
    def _columns(self) -> str:
        return ", ".join(self.kind.columns)

    def _line(self, row: tuple) -> str:
        if self.kind.columns == ("doc",):
            return row[0] + "\n"
        return json.dumps(dict(zip(self.kind.columns, row)), separators=(",", ":")) + "\n"

    def _open(self, mode: str) -> sqlite3.Connection | None:
        """A connection of its own, or None when there is nothing to open.

        Its own, so a download neither creates the file nor waits behind a
        write, and a long import does not hold the lock the server adds
        documents under any longer than its own transaction.
        """
        try:
            db = sqlite3.connect(f"file:{self.path}?mode={mode}", uri=True,
                                 timeout=BUSY_SECONDS)
        except sqlite3.Error:
            return None
        try:
            db.execute(f"SELECT 1 FROM {self.table} LIMIT 1")
        except sqlite3.Error:
            db.close()
            return None
        return db
