"""The splash screen while the page schedule is off.

A range with an interval of 0 turns page changes off, and the display then
sleeps until the next range that is on. The page it slept on would show its
readings for hours as if they were current. So the display gets the splash
instead: a wake at the start of each stretch that is off, and the splash for
any page it fetches during one, such as the first after a restart at night.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Callable

from epd_server.scheduling import TimeRangesSchedule, WakeSchedule
from epd_server.timeranges import Week
from flask import Flask

MINUTE = 60


def interval_at(week: Week, t: float) -> int:
    """The interval of the range that the minute holding ``t`` is in; 0 when off."""
    local = datetime.fromtimestamp(math.floor(t) // MINUTE * MINUTE, week.tz)
    return week.on(local.weekday()).every_at(local.time())


class OffHoursSchedule(WakeSchedule):
    """``inner``, with a wake for the page ``splash`` at each minute where a
    range that is on gives way to one that is off."""

    def __init__(self, inner: TimeRangesSchedule, splash: str):
        self.inner = inner
        self.week = inner.week
        self.tz = inner.tz
        self.splash = splash

    def is_off(self, t: float) -> bool:
        return interval_at(self.week, t) == 0

    def off_start_before(self, t: float, end: float) -> int | None:
        """The first start of an off stretch after ``t`` and before ``end``,
        in epoch seconds. One at ``t`` has passed, as for a slot."""
        minute = (math.floor(t) // MINUTE + 1) * MINUTE
        on = not self.is_off(minute - MINUTE)
        while minute < end:
            off = self.is_off(minute)
            if on and off:
                return minute
            on = not off
            minute += MINUTE
        return None

    def next_wake(self, now=None):
        now = now if now is not None else datetime.now(tz=self.tz)
        wake, page = self.inner.next_wake(now=now)
        off = self.off_start_before(now.timestamp(), wake.timestamp())
        if off is None:
            return wake, page
        return datetime.fromtimestamp(off, self.tz), self.splash

    def next_regen(self, lead_seconds=120, now=None):
        now = now if now is not None else datetime.now(tz=self.tz)
        regen, wake, page = self.inner.next_regen(lead_seconds=lead_seconds, now=now)
        off = self.off_start_before(now.timestamp() + lead_seconds, wake.timestamp())
        if off is None:
            return regen, wake, page
        off_dt = datetime.fromtimestamp(off, self.tz)
        return off_dt - timedelta(seconds=lead_seconds), off_dt, self.splash

    def pages(self):
        return self.inner.pages() | {self.splash}

    def describe(self):
        return {**self.inner.describe(), "off": self.splash}


def splash_when_off(app: Flask, schedule: OffHoursSchedule, endpoints: list[str],
                    splash_endpoint: str, clock: Callable[[], float]) -> None:
    """Answer each page in ``endpoints`` with the splash while the schedule
    is off. Each page's route is DisplayServer's, under the page's name."""
    splash = app.view_functions[splash_endpoint]

    def or_splash(view):
        def serve():
            return splash() if schedule.is_off(clock()) else view()
        serve.__name__ = view.__name__
        return serve

    for endpoint in endpoints:
        if endpoint != splash_endpoint:
            app.view_functions[endpoint] = or_splash(app.view_functions[endpoint])
