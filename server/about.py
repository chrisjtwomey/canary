"""``GET /about``: what this server is, so a board can decide what to do.

A board asks at boot, after a post the server would not take, and once an
hour. It carries the same version and clock the response headers carry, and
adds what only a document has room for: the firmware each board is offered,
which library this server is built on, and each board's sync schedule.

The config page asks after a save, until the server names the config it saved.
"""
from __future__ import annotations

import hashlib
import time
from typing import Callable

from epd_server import __version__ as library_version
from epd_server.config import FirmwareSettings
from epd_server.firmware import FirmwareStore

from epd_server.timeranges import Week


def config_version(text: str) -> str:
    """Eight hex digits that change whenever config.yaml's text does."""
    return hashlib.sha1(text.encode()).hexdigest()[:8]


class About:
    """The answer to ``GET /about``.

    Args:
        version: what this server calls itself.
        firmware: the firmware settings, so the answer can name the image on
            offer to each board: the newest that can work with ``version``.
            Without them the answer says there is none.
        now: the clock, for tests.
        syncs: each board's sync schedule, by its short name, when the
            server keeps them.
        config: the config_version of the config.yaml the server started on.
    """

    def __init__(self, version: str, firmware: FirmwareSettings | None = None,
                 now: Callable[[], float] = time.time,
                 syncs: dict[str, Week] | None = None, config: str | None = None):
        self.version = version
        self.firmware = firmware
        self.now = now
        self.syncs = syncs or {}
        self.config = config
        self.stores = ({p: FirmwareStore(firmware.dir_for(p)) for p in firmware.names()}
                       if firmware and firmware.enabled else {})

    def answer(self, args: dict) -> dict:
        now = self.now()
        server = {"version": self.version, "library": library_version, "epoch": int(now)}
        if self.config is not None:
            server["config"] = self.config
        return {
            "server": server,
            "firmware": self._firmware(),
            "sync": self._sync(now),
        }

    def _sync(self, now: float) -> dict | None:
        """Each board's week of ranges and the seconds to its next slot."""
        if not self.syncs:
            return None
        return {board: {"week": sync.describe(), "next_s": sync.seconds_until_next(now)}
                for board, sync in self.syncs.items()}

    def _firmware(self) -> dict | None:
        """Each product's offer, None where the server holds nothing its
        version can work with."""
        if not self.stores:
            return None
        offers = {p: store.newest_compatible(self.version) for p, store in self.stores.items()}
        return {p: image.version if image else None for p, image in offers.items()}
