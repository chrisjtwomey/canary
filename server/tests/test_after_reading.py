"""Each page made after the dock's reading at its slot, and the display's wake
after that."""
from datetime import datetime
from zoneinfo import ZoneInfo

from epd_server.timeranges import TimeRanges, parse_hhmm

from after_reading import READING_WAIT_S, AfterReadingSchedule
from off_hours import OffHoursSchedule
from server import load_settings, make_next_sync, make_sensor_poll

DUBLIN = ZoneInfo("Europe/Dublin")
LEAD_S = 10
# Off from midnight on weekdays, on from 08:30 with a page every 15 minutes.
WEEK = [{"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
         "ranges": [{"from": "00:00", "every": 0}, {"from": "08:30", "every": 900}]}]


def at(day, hour, minute, second=0):
    """A local time in October 2026: the 1st is a Thursday."""
    return datetime(2026, 10, day, hour, minute, second, tzinfo=DUBLIN)


def schedule(lead_s=LEAD_S):
    settings = load_settings({"server": {"timezone": "Europe/Dublin"},
                              "display": {"pools": {"co2": ["breathe.png"]}, "schedule": {
                                  "type": "timeranges", "week": WEEK}}})
    return AfterReadingSchedule(OffHoursSchedule(settings.core.server.schedule, "splash.png"), lead_s)


def test_the_page_renders_after_its_slot_and_the_display_wakes_the_lead_after_that():
    regen, wake, page = schedule().next_regen(lead_seconds=LEAD_S, now=at(2, 11, 59, 0))
    assert regen == at(2, 12, 0, READING_WAIT_S)
    assert wake == at(2, 12, 0, READING_WAIT_S + LEAD_S)
    assert page == "breathe.png"
    assert schedule().next_wake(now=at(2, 11, 59, 0)) == (wake, page)


def test_a_slot_that_has_passed_still_has_its_wake_to_come():
    assert schedule().next_wake(now=at(2, 12, 0, 5))[0] == at(2, 12, 0, 20)
    assert schedule().next_regen(lead_seconds=LEAD_S, now=at(2, 12, 0, 5))[0] == at(2, 12, 0, 10)


def test_a_display_on_its_wake_is_sent_to_the_next():
    assert schedule().next_wake(now=at(2, 12, 0, 20))[0] == at(2, 12, 15, 20)
    assert schedule().next_regen(lead_seconds=LEAD_S, now=at(2, 12, 0, 12))[0] == at(2, 12, 15, 10)


def test_the_wake_moves_with_the_pre_render():
    assert schedule(lead_s=30).next_wake(now=at(2, 11, 59, 0))[0] == at(2, 12, 0, 40)


def test_the_splash_wake_comes_after_its_minute_too():
    assert schedule().next_wake(now=at(1, 23, 50)) == (at(2, 0, 0, 20), "splash.png")


def test_a_display_sync_just_before_a_page_wake_moves_to_that_wake():
    display = TimeRanges([(parse_hhmm("00:00"), 900)], DUBLIN, "display.sync")
    s = schedule()
    syncs = {"canary-display": display}
    now = at(2, 12, 0, 21).timestamp()
    # The 12:15 sync comes 20 s before the 12:15 page's wake, which posts the state anyway.
    assert make_next_sync(syncs, s.page_wake)("canary-display", now) == 15 * 60 - 1
    assert make_sensor_poll(syncs, s.page_wake)(now, "canary-display") == 15 * 60 - 1
    assert make_next_sync(syncs)("canary-display", now) == 15 * 60 - 21


def test_a_display_sync_away_from_any_page_wake_stays():
    display = TimeRanges([(parse_hhmm("00:00"), 900)], DUBLIN, "display.sync")
    pages_every_20 = [{"days": WEEK[0]["days"], "ranges": [{"from": "00:00", "every": 1200}]}]
    settings = load_settings({"server": {"timezone": "Europe/Dublin"},
                              "display": {"pools": {"co2": ["breathe.png"]}, "schedule": {
                                  "type": "timeranges", "week": pages_every_20}}})
    s = AfterReadingSchedule(OffHoursSchedule(settings.core.server.schedule, "splash.png"), LEAD_S)
    now = at(2, 12, 0, 21).timestamp()
    # The next page wake is 12:20:20; the 12:15 sync is 5 minutes before it.
    assert make_next_sync({"canary-display": display}, s.page_wake)("canary-display", now) == \
        15 * 60 - 21


def test_the_dock_keeps_its_own_slots():
    dock = TimeRanges([(parse_hhmm("00:00"), 300)], DUBLIN, "dock.sync")
    now = at(2, 12, 0, 21).timestamp()
    assert make_next_sync({"canary-dock": dock}, schedule().page_wake)("canary-dock", now) == \
        5 * 60 - 21


def test_page_wake_gives_the_wake_and_how_long_after_its_slot_it_comes():
    wake, after_slot = schedule().page_wake(at(2, 11, 59).timestamp())
    assert wake == at(2, 12, 0, 20).timestamp() and after_slot == READING_WAIT_S + LEAD_S
