"""When the dock posts its readings: slots on the wall clock, slower overnight.

A slot is a local time whose seconds past midnight are a multiple of the
interval: :00, :05, :10 ... for five minutes, the hour and the half hour for
thirty. Inside the quiet window the quiet interval applies. The dock asks
nothing but "how long until the next one", which this answers.

The window is judged in local time, one minute at a time, rather than by
working out where its edges fall. Some clocks change at 01:00, the window's
own start: in spring 01:00 to 02:00 never happens, and in autumn it happens
twice. Stepping through the minutes and asking of each whether it is inside
gets both right without a special case.
"""
from __future__ import annotations

import math
from datetime import datetime, time as clock_time, tzinfo

# The slots fall on whole minutes, so every interval is a whole number of them.
MINUTE = 60
# Two days of minutes: further than any gap between two slots can be.
LOOK_AHEAD_MINUTES = 2 * 24 * 60
# The dock posts every half hour overnight unless config.yaml says otherwise.
DEFAULT_QUIET = {"from": "01:00", "to": "07:00", "every": 1800}


def parse_hhmm(text: str) -> clock_time:
    """``"01:00"`` as a time of day.

    Raises:
        ValueError: it is not ``HH:MM``.
    """
    try:
        hours, minutes = str(text).split(":")
        return clock_time(int(hours), int(minutes))
    except ValueError:
        raise ValueError(f"{text!r} is not a time of day as HH:MM") from None


def _interval(seconds, name: str) -> int:
    if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0 \
            or seconds % MINUTE:
        raise ValueError(f"{name} must be a whole number of minutes in seconds, not {seconds!r}")
    return seconds


class PostSchedule:
    """The dock's post slots.

    Args:
        every: the interval outside the quiet window, in seconds.
        tz: the zone the slots and the window are in.
        quiet_from, quiet_to: the window, as times of day; it may run past
            midnight. Both or neither.
        quiet_every: the interval inside the window.

    Raises:
        ValueError: an interval is not a whole number of minutes, or the
            window is half given or empty.
    """

    def __init__(self, every: int, tz: tzinfo, quiet_from: clock_time | None = None,
                 quiet_to: clock_time | None = None, quiet_every: int | None = None):
        self.every = _interval(every, "posts.every")
        self.tz = tz
        if (quiet_from is None) != (quiet_to is None):
            raise ValueError("posts.quiet needs both from and to")
        if quiet_from is not None and quiet_from == quiet_to:
            raise ValueError("posts.quiet starts and ends at the same time")
        self.quiet_from = quiet_from
        self.quiet_to = quiet_to
        self.quiet_every = _interval(quiet_every if quiet_every is not None else every,
                                     "posts.quiet.every")

    def quiet(self, local: datetime) -> bool:
        """Whether a local time is inside the quiet window."""
        if self.quiet_from is None:
            return False
        t = local.time()
        if self.quiet_from < self.quiet_to:
            return self.quiet_from <= t < self.quiet_to
        return t >= self.quiet_from or t < self.quiet_to

    def seconds_until_next(self, now: float) -> int:
        """Whole seconds until the first slot after ``now``, rounded up so a
        board that waits this long is never early for it."""
        minute = (math.floor(now) // MINUTE + 1) * MINUTE
        for _ in range(LOOK_AHEAD_MINUTES):
            local = datetime.fromtimestamp(minute, self.tz)
            step = self.quiet_every if self.quiet(local) else self.every
            if (local.hour * 3600 + local.minute * 60) % step == 0:
                return max(1, math.ceil(minute - now))
            minute += MINUTE
        raise AssertionError("no slot in two days")   # an interval divides some minute of the day

    def slot_before(self, t: float) -> int:
        """The latest slot at or before ``t``."""
        minute = math.floor(t) // MINUTE * MINUTE
        for _ in range(LOOK_AHEAD_MINUTES):
            local = datetime.fromtimestamp(minute, self.tz)
            step = self.quiet_every if self.quiet(local) else self.every
            if (local.hour * 3600 + local.minute * 60) % step == 0:
                return minute
            minute -= MINUTE
        raise AssertionError("no slot in two days")

    def describe(self) -> dict:
        """The schedule as ``GET /about`` gives it."""
        quiet = None
        if self.quiet_from is not None:
            quiet = {"from": self.quiet_from.strftime("%H:%M"),
                     "to": self.quiet_to.strftime("%H:%M"), "every": self.quiet_every}
        return {"every": self.every, "quiet": quiet}
