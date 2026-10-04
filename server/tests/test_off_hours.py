"""The splash screen while the page schedule is off: a wake at the start of
each stretch that is off, and the splash for any page fetched in one."""
from datetime import datetime
from zoneinfo import ZoneInfo

from epd_server import DisplayServer

from off_hours import OffHoursSchedule, splash_when_off
from pages.splash import SplashPage, logo_svg
from server import load_settings, make_pages
from sources.mock import MockReadingsSource

DUBLIN = ZoneInfo("Europe/Dublin")
POOLS = {"co2": ["breathe.png"]}
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]
WEEKEND = ["sat", "sun"]
# Off from midnight on weekdays and from 01:00 at weekends, on from 08:30.
WEEK = [{"days": WEEKDAYS, "ranges": [{"from": "00:00", "every": 0}, {"from": "08:30", "every": 900}]},
        {"days": WEEKEND, "ranges": [{"from": "01:00", "every": 0}, {"from": "08:30", "every": 1200}]}]


def at(day, hour, minute, second=0):
    """A local time in October 2026: the 1st is a Thursday."""
    return datetime(2026, 10, day, hour, minute, second, tzinfo=DUBLIN)


def schedule(week=WEEK):
    settings = load_settings({"server": {"timezone": "Europe/Dublin"},
                              "display": {"pools": POOLS, "schedule": {
                                  "type": "timeranges", "week": week}}})
    return OffHoursSchedule(settings.core.server.schedule, "splash.png")


def test_the_splash_comes_when_the_pages_turn_off():
    assert schedule().next_wake(now=at(1, 23, 50)) == (at(2, 0, 0), "splash.png")


def test_after_the_splash_the_next_page_comes_when_they_turn_on():
    assert schedule().next_wake(now=at(2, 0, 0, 5)) == (at(2, 8, 30), "breathe.png")


def test_a_day_turns_off_by_its_own_ranges():
    # Saturday runs its own last range until 01:00, so Friday night carries on,
    # at that range's slots: 20 minutes apart from 08:30.
    assert schedule().next_wake(now=at(2, 23, 50)) == (at(3, 0, 10), "breathe.png")
    assert schedule().next_wake(now=at(3, 0, 50)) == (at(3, 1, 0), "splash.png")


def test_a_schedule_that_is_never_off_is_unchanged():
    week = [{"days": WEEKDAYS + WEEKEND, "ranges": [{"from": "00:00", "every": 3600}]}]
    s = schedule(week)
    assert s.next_wake(now=at(1, 23, 50)) == s.inner.next_wake(now=at(1, 23, 50))


def test_the_splash_renders_ahead_of_its_wake_as_a_page_does():
    assert schedule().next_regen(lead_seconds=120, now=at(1, 23, 50)) == (
        at(1, 23, 58), at(2, 0, 0), "splash.png")


def test_the_schedule_names_the_splash_among_its_pages():
    assert schedule().pages() == {"breathe.png", "splash.png"}


def test_the_hours_that_are_off_are_the_ranges_with_no_interval():
    s = schedule()
    assert s.is_off(at(2, 0, 0).timestamp()) and s.is_off(at(2, 8, 29).timestamp())
    assert not s.is_off(at(2, 8, 30).timestamp())
    assert not s.is_off(at(3, 0, 30).timestamp())


def test_a_page_fetched_while_off_is_the_splash(tmp_path):
    pages = [p for p in make_pages(DUBLIN, width=1280, height=720, png_dir=tmp_path)
             if p.png_filename == "breathe.png"]
    splash = SplashPage(logo_svg(), width=1280, height=720, png_dir=tmp_path)
    for page, body in ((pages[0], b"breathe"), (splash, b"splash")):
        with open(page.png_path, "wb") as f:
            f.write(body)
    s = schedule()
    server = DisplayServer(pages=[*pages, splash], source=MockReadingsSource(), schedule=s,
                           tz=DUBLIN)
    now = at(2, 3, 0).timestamp()
    splash_when_off(server.app, s, [p.name for p in pages], splash.name, lambda: now)
    client = server.app.test_client()

    assert client.get("/breathe.png").data == b"splash"
    assert client.get("/splash.png").data == b"splash"
    now = at(2, 9, 0).timestamp()
    assert client.get("/breathe.png").data == b"breathe"
