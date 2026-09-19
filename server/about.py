"""``GET /about``: what this server is, so a board can decide what to do.

A board asks at boot, after a post the server would not take, and once an
hour. It carries the same version and clock the response headers carry, and
adds what only a document has room for: the firmware each board is offered,
which library this server is built on, and the dock's post schedule.
"""
from __future__ import annotations

import time
from typing import Callable

from epd_server import __version__ as library_version
from epd_server.config import FirmwareSettings
from epd_server.firmware import FirmwareStore

from schedule import PostSchedule


class About:
    """The answer to ``GET /about``.

    Args:
        version: what this server calls itself.
        firmware: the firmware settings, so the answer can name the image on
            offer to each board: the newest that can work with ``version``.
            Without them the answer says there is none.
        now: the clock, for tests.
        posts: the dock's post schedule, when the server keeps one.
    """

    def __init__(self, version: str, firmware: FirmwareSettings | None = None,
                 now: Callable[[], float] = time.time, posts: PostSchedule | None = None):
        self.version = version
        self.firmware = firmware
        self.now = now
        self.posts = posts
        self.stores = ({p: FirmwareStore(firmware.dir_for(p)) for p in firmware.names()}
                       if firmware and firmware.enabled else {})

    def answer(self, args: dict) -> dict:
        now = self.now()
        return {
            "server": {
                "version": self.version,
                "library": library_version,
                "epoch": int(now),
            },
            "firmware": self._firmware(),
            "posts": self._posts(now),
        }

    def _posts(self, now: float) -> dict | None:
        if self.posts is None:
            return None
        return {**self.posts.describe(), "next_s": self.posts.seconds_until_next(now)}

    def _firmware(self) -> dict | None:
        """Each product's offer, None where the server holds nothing its
        version can work with."""
        if not self.stores:
            return None
        offers = {p: store.newest_compatible(self.version) for p, store in self.stores.items()}
        return {p: image.version if image else None for p, image in offers.items()}
