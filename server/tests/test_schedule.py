"""The dock's post slots: every five minutes, every half hour overnight."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from schedule import PostSchedule, parse_hhmm

DUBLIN = ZoneInfo("Europe/Dublin")


def schedule(**kw):
    kw = {"quiet_from": parse_hhmm("01:00"), "quiet_to": parse_hhmm("07:00"),
          "quiet_every": 1800, **kw}
    return PostSchedule(300, DUBLIN, **kw)


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=DUBLIN).timestamp()


def next_slot(s, text):
    now = at(text)
    return datetime.fromtimestamp(now + s.seconds_until_next(now), DUBLIN).strftime("%m-%d %H:%M:%S")


@pytest.mark.parametrize("now, slot", [
    ("2026-06-15T12:03:10", "06-15 12:05:00"),
    ("2026-06-15T12:05:00", "06-15 12:10:00"),     # a board on the slot is sent to the next
    ("2026-06-15T12:04:59.5", "06-15 12:05:00"),
    ("2026-06-15T00:58:00", "06-15 01:00:00"),     # the window's start is a slot in both
    ("2026-06-15T01:00:00", "06-15 01:30:00"),
    ("2026-06-15T02:10:00", "06-15 02:30:00"),
    ("2026-06-15T06:40:00", "06-15 07:00:00"),
    ("2026-06-15T07:00:30", "06-15 07:05:00"),
    ("2026-06-15T23:58:00", "06-16 00:00:00"),
])
def test_slots_fall_on_the_wall_clock(now, slot):
    assert next_slot(schedule(), now) == slot


def test_it_never_sends_a_board_early():
    s = schedule()
    now = at("2026-06-15T12:03:10.4")
    assert now + s.seconds_until_next(now) >= at("2026-06-15T12:05:00")


def test_spring_forward_skips_the_hour_that_does_not_happen():
    # 29 March 2026: 01:00 GMT becomes 02:00 IST, so 00:55 is five minutes from 02:00.
    s = schedule()
    now = at("2026-03-29T00:55:00")
    assert s.seconds_until_next(now) == 300
    assert datetime.fromtimestamp(now + 300, DUBLIN).strftime("%H:%M") == "02:00"


def test_fall_back_keeps_the_half_hour_through_the_repeated_hour():
    # 25 October 2026: 02:00 IST becomes 01:00 GMT, and 01:00 to 02:00 happens twice.
    s = schedule()
    t = datetime(2026, 10, 25, 0, 56, tzinfo=DUBLIN).timestamp()
    slots = []
    for _ in range(6):
        t += s.seconds_until_next(t)
        slots.append(datetime.fromtimestamp(t, DUBLIN).strftime("%H:%M%z"))
    assert slots == ["01:00+0100", "01:30+0100", "01:00+0000", "01:30+0000",
                     "02:00+0000", "02:30+0000"]


def test_a_window_past_midnight():
    s = schedule(quiet_from=parse_hhmm("23:00"), quiet_to=parse_hhmm("06:00"))
    assert next_slot(s, "2026-06-15T23:10:00") == "06-15 23:30:00"
    assert next_slot(s, "2026-06-15T05:40:00") == "06-15 06:00:00"
    assert next_slot(s, "2026-06-15T06:00:00") == "06-15 06:05:00"


def test_without_a_window_every_slot_is_the_same():
    s = PostSchedule(300, DUBLIN)
    assert next_slot(s, "2026-06-15T02:10:00") == "06-15 02:15:00"
    assert s.describe() == {"every": 300, "quiet": None}


def test_it_describes_itself_for_about():
    assert schedule().describe() == {"every": 300,
                                     "quiet": {"from": "01:00", "to": "07:00", "every": 1800}}


@pytest.mark.parametrize("kw", [
    {"every": 0}, {"every": 90}, {"every": "300"},
    {"quiet_every": 45},
    {"quiet_to": None},
    {"quiet_from": parse_hhmm("01:00"), "quiet_to": parse_hhmm("01:00")},
])
def test_a_schedule_that_cannot_work_is_refused(kw):
    args = {"every": 300, "tz": DUBLIN, "quiet_from": parse_hhmm("01:00"),
            "quiet_to": parse_hhmm("07:00"), "quiet_every": 1800, **kw}
    with pytest.raises(ValueError):
        PostSchedule(**args)


@pytest.mark.parametrize("text", ["1am", "25:00", "01:00:00", ""])
def test_a_time_of_day_must_be_hh_mm(text):
    with pytest.raises(ValueError):
        parse_hhmm(text)


def test_config_without_a_posts_block_keeps_the_quiet_night():
    from server import make_posts
    assert make_posts({}, DUBLIN).describe() == schedule().describe()


def test_config_can_turn_the_quiet_window_off_or_move_it():
    from server import make_posts
    assert make_posts({"posts": {"every": 600, "quiet": {}}}, DUBLIN).describe() == \
        {"every": 600, "quiet": None}
    moved = make_posts({"posts": {"quiet": {"from": "23:00", "to": "06:00", "every": 3600}}}, DUBLIN)
    assert moved.describe()["quiet"] == {"from": "23:00", "to": "06:00", "every": 3600}


@pytest.mark.parametrize("now, slot", [
    ("2026-06-15T12:03:10", "06-15 12:00:00"),
    ("2026-06-15T12:05:00", "06-15 12:05:00"),     # a slot is its own latest
    ("2026-06-15T01:20:00", "06-15 01:00:00"),     # quiet: on the half hour
    ("2026-06-15T07:03:00", "06-15 07:00:00"),
    ("2026-06-15T06:59:00", "06-15 06:30:00"),
])
def test_the_latest_slot_at_or_before_a_time(now, slot):
    assert datetime.fromtimestamp(schedule().slot_before(at(now)), DUBLIN).strftime(
        "%m-%d %H:%M:%S") == slot
