"""``GET /about``: what this server is, so a board can decide what to do.

A board asks at boot, after a post the server would not take, and once an
hour. It carries the same version and clock the response headers carry, and
adds what only a document has room for: the firmware on offer, and which
library this server is built on.
"""
from __future__ import annotations

import time
from typing import Callable

from epd_server import __version__ as library_version
from epd_server.config import FirmwareSettings
from epd_server.firmware import FirmwareStore


class About:
    """The answer to ``GET /about``.

    Args:
        version: what this server calls itself.
        firmware: the firmware settings, so the answer can name the image on
            offer. Without them the answer says there is none.
        now: the clock, for tests.
    """

    def __init__(self, version: str, firmware: FirmwareSettings | None = None,
                 now: Callable[[], float] = time.time):
        self.version = version
        self.firmware = firmware
        self.now = now
        self.store = FirmwareStore(firmware.dir) if firmware and firmware.enabled else None

    def answer(self, args: dict) -> dict:
        return {
            "server": {
                "version": self.version,
                "library": library_version,
                "epoch": int(self.now()),
            },
            "firmware": self._firmware(),
        }

    def _firmware(self) -> dict | None:
        if self.store is None or self.firmware is None:
            return None
        image = self.store.current()
        if image is None:
            return None
        return {"product": self.firmware.product, "version": image.version}
