"""Each page made after the dock's reading at its slot.

The dock reads at its slots and the display changes page at its own, and the
two share minutes: a page made before its slot holds the reading from the
slot before, up to five minutes old. So each page renders READING_WAIT_S after
its slot, once the dock's reading is in, and the display wakes the pre-render
after that.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from epd_server.scheduling import WakeSchedule

# The dock posts its reading about 1.5 s after its slot; the rest is for a
# slow Wi-Fi.
READING_WAIT_S = 10


class AfterReadingSchedule(WakeSchedule):
    """``inner``, with each page rendered READING_WAIT_S after its slot and
    each wake ``lead_seconds`` after that."""

    def __init__(self, inner: WakeSchedule, lead_seconds: int, wait_seconds: int = READING_WAIT_S):
        self.inner = inner
        self.tz = inner.tz
        self.wait = timedelta(seconds=wait_seconds)
        self.after_slot = timedelta(seconds=wait_seconds + lead_seconds)

    def next_wake(self, now=None):
        now = now if now is not None else datetime.now(tz=self.tz)
        slot, page = self.inner.next_wake(now=now - self.after_slot)
        return slot + self.after_slot, page

    def next_regen(self, lead_seconds=120, now=None):
        now = now if now is not None else datetime.now(tz=self.tz)
        slot, page = self.inner.next_wake(now=now - self.wait)
        regen = slot + self.wait
        return regen, regen + timedelta(seconds=lead_seconds), page

    def page_wake(self, now: float) -> tuple[float, float]:
        """The next wake after ``now``, and how long after its slot it comes,
        both in seconds."""
        wake, _ = self.next_wake(now=datetime.fromtimestamp(now, self.tz))
        return wake.timestamp(), self.after_slot.total_seconds()

    def pages(self):
        return self.inner.pages()

    def describe(self):
        return self.inner.describe()
