"""Whether the display runs the saved Display and Image settings.

The display keeps none of them: at each sync the server chooses the display's
next page and the time to its next wake from config.yaml's ``display`` and
``image`` blocks. So the server takes a version of those blocks when it starts
and stamps each report from the display with it (DeviceReports' ``stamps``).
The display runs the saved settings once its newest report carries the
version the server runs now.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from typing import Callable

from epd_server.timeranges import Week

DISPLAY = "canary-display"


def display_version(config: dict) -> str:
    """Eight hex digits that change whenever the display or image block does."""
    blocks = {key: config.get(key) for key in ("display", "image")}
    text = json.dumps(blocks, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(text.encode()).hexdigest()[:8]


class DisplaySync:
    """What the Display tab says about the display beside its settings.

    Args:
        version: the display_version of the config the server runs.
        sync: the display's sync schedule.
        reported: what the server knows of a board, as DeviceReports.device
            gives it.
    """

    def __init__(self, version: str, sync: Week,
                 reported: Callable[[str], dict | None],
                 now: Callable[[], float] = time.time):
        self.version = version
        self.sync = sync
        self.reported = reported
        self.now = now

    def _entry(self) -> dict:
        return self.reported(DISPLAY) or {}

    def applied(self) -> bool | None:
        """Whether the display runs these settings, None before it has reported."""
        doc = self._entry().get("doc")
        if not doc:
            return None
        return doc.get("settings_version") == self.version

    def offline(self) -> tuple[bool, int | None]:
        """Whether the display has missed two of its slots, and how long ago
        it last reported. Not offline before its first report."""
        entry = self._entry()
        return bool(entry.get("offline")), entry.get("age_s")

    def next_sync(self) -> str:
        """The local time of the display's next slot, as HH:MM; empty when it has none."""
        now = self.now()
        wait = self.sync.seconds_until_next(now)
        return "" if wait is None else datetime.fromtimestamp(now + wait, self.sync.tz).strftime("%H:%M")
