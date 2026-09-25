"""A board's sync slots: ranges round the clock, each with its interval."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from schedule import DEFAULT_DOCK_SYNC, MAX_RANGES, ClockSchedule, in_window, parse_hhmm

DUBLIN = ZoneInfo("Europe/Dublin")


def clock(*ranges):
    """A schedule of ``("HH:MM", every)`` pairs; by default the dock's own."""
    if not ranges:
        ranges = tuple((r["from"], r["every"]) for r in DEFAULT_DOCK_SYNC)
    return ClockSchedule([(parse_hhmm(start), every) for start, every in ranges], DUBLIN,
                         "dock.sync")


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=DUBLIN).timestamp()


def next_slot(s, text):
    now = at(text)
    return datetime.fromtimestamp(now + s.seconds_until_next(now), DUBLIN).strftime("%m-%d %H:%M:%S")


@pytest.mark.parametrize("now, slot", [
    ("2026-06-15T12:03:10", "06-15 12:05:00"),
    ("2026-06-15T12:05:00", "06-15 12:10:00"),     # a board on the slot is sent to the next
    ("2026-06-15T12:04:59.5", "06-15 12:05:00"),
    ("2026-06-15T00:58:00", "06-15 01:00:00"),     # a range's start is a slot in both
    ("2026-06-15T01:00:00", "06-15 01:30:00"),
    ("2026-06-15T02:10:00", "06-15 02:30:00"),
    ("2026-06-15T06:40:00", "06-15 07:00:00"),
    ("2026-06-15T07:00:30", "06-15 07:05:00"),
    ("2026-06-15T23:58:00", "06-16 00:00:00"),
])
def test_slots_fall_on_the_wall_clock(now, slot):
    assert next_slot(clock(), now) == slot


def test_it_never_sends_a_board_early():
    s = clock()
    now = at("2026-06-15T12:03:10.4")
    assert now + s.seconds_until_next(now) >= at("2026-06-15T12:05:00")


def test_spring_forward_skips_the_hour_that_does_not_happen():
    # 29 March 2026: 01:00 GMT becomes 02:00 IST, so 00:55 is five minutes from 02:00.
    s = clock()
    now = at("2026-03-29T00:55:00")
    assert s.seconds_until_next(now) == 300
    assert datetime.fromtimestamp(now + 300, DUBLIN).strftime("%H:%M") == "02:00"


def test_fall_back_keeps_the_half_hour_through_the_repeated_hour():
    # 25 October 2026: 02:00 IST becomes 01:00 GMT, and 01:00 to 02:00 happens twice.
    s = clock()
    t = datetime(2026, 10, 25, 0, 56, tzinfo=DUBLIN).timestamp()
    slots = []
    for _ in range(6):
        t += s.seconds_until_next(t)
        slots.append(datetime.fromtimestamp(t, DUBLIN).strftime("%H:%M%z"))
    assert slots == ["01:00+0100", "01:30+0100", "01:00+0000", "01:30+0000",
                     "02:00+0000", "02:30+0000"]


def test_a_range_can_run_past_midnight():
    s = clock(("06:00", 300), ("23:00", 1800))
    assert next_slot(s, "2026-06-15T23:10:00") == "06-15 23:30:00"
    assert next_slot(s, "2026-06-15T05:40:00") == "06-15 06:00:00"
    assert next_slot(s, "2026-06-15T06:00:00") == "06-15 06:05:00"


def test_one_range_is_the_whole_day():
    s = clock(("09:00", 600))
    assert next_slot(s, "2026-06-15T02:13:00") == "06-15 02:20:00"
    assert s.describe() == [{"from": "09:00", "every": 600}]


def test_a_range_that_is_off_has_no_slots():
    s = clock(("07:00", 300), ("22:00", 0))
    assert next_slot(s, "2026-06-15T22:00:00") == "06-16 07:00:00"
    assert next_slot(s, "2026-06-16T03:00:00") == "06-16 07:00:00"


def test_the_start_of_a_range_that_is_off_is_not_a_slot():
    s = clock(("07:00", 300), ("22:00", 0))
    assert next_slot(s, "2026-06-15T21:57:00") == "06-16 07:00:00"


def test_many_ranges_each_keep_their_own_interval():
    s = clock(("00:00", 3600), ("07:00", 300), ("12:00", 60), ("13:00", 300), ("22:00", 0))
    assert next_slot(s, "2026-06-15T03:10:00") == "06-15 04:00:00"
    assert next_slot(s, "2026-06-15T12:10:30") == "06-15 12:11:00"
    assert next_slot(s, "2026-06-15T13:01:00") == "06-15 13:05:00"
    assert next_slot(s, "2026-06-15T22:30:00") == "06-16 00:00:00"


def test_a_schedule_with_every_range_off_has_no_next_slot():
    s = clock(("07:00", 0), ("22:00", 0))
    assert s.seconds_until_next(at("2026-06-15T12:00:00")) is None
    assert s.slot_before(at("2026-06-15T12:00:00")) is None


def test_it_describes_itself_from_the_earliest_start():
    assert clock().describe() == [{"from": "01:00", "every": 1800},
                                  {"from": "07:00", "every": 300}]


@pytest.mark.parametrize("ranges, words", [
    ((), "at least one range"),
    ((("07:00", 300),) * 2, "two ranges from 07:00"),
    (tuple((f"{h:02d}:00", 300) for h in range(MAX_RANGES + 1)), "the most is 8"),
    ((("07:00", 90),), "whole number of minutes"),
    ((("07:00", -60),), "whole number of minutes"),
    ((("07:00", "300"),), "whole number of minutes"),
    ((("07:00", True),), "whole number of minutes"),
    ((("07:00", 24 * 3600 + 60),), "up to a day"),
])
def test_a_schedule_that_cannot_work_is_refused(ranges, words):
    with pytest.raises(ValueError, match=words):
        ClockSchedule([(parse_hhmm(s), e) for s, e in ranges], DUBLIN, "dock.sync")


@pytest.mark.parametrize("value, words", [
    ({"every": 300}, "must be a list of ranges"),
    ([{"from": "07:00"}], "exactly from and every"),
    ([{"from": "07:00", "every": 300, "to": "08:00"}], "exactly from and every"),
    ([{"from": "7am", "every": 300}], "not a time of day"),
    ([{"from": 420, "every": 300}], "not a time of day"),   # an unquoted 07:00 is a number
])
def test_a_config_value_that_is_not_a_schedule_is_refused(value, words):
    with pytest.raises(ValueError, match=words):
        ClockSchedule.from_config(value, DUBLIN, "dock.sync")


def test_every_message_starts_with_the_key():
    with pytest.raises(ValueError, match="^dock.sync"):
        ClockSchedule.from_config([{"from": "07:00", "every": 7}], DUBLIN, "dock.sync")


@pytest.mark.parametrize("text", ["1am", "25:00", "01:00:00", ""])
def test_a_time_of_day_must_be_hh_mm(text):
    with pytest.raises(ValueError):
        parse_hhmm(text)


def test_config_without_a_schedule_keeps_the_slower_night():
    from server import make_dock_sync
    assert make_dock_sync({}, DUBLIN).describe() == clock().describe()


def test_config_can_set_the_ranges():
    from server import make_dock_sync
    sync = make_dock_sync({"dock": {"sync": [{"from": "23:00", "every": 3600},
                                             {"from": "06:00", "every": 600}]}}, DUBLIN)
    assert sync.describe() == [{"from": "06:00", "every": 600}, {"from": "23:00", "every": 3600}]


def test_the_dock_must_sync_in_some_range():
    from epd_server.config import ConfigError
    from server import make_dock_sync
    with pytest.raises(ConfigError, match="^dock.sync has no range that syncs"):
        make_dock_sync({"dock": {"sync": [{"from": "00:00", "every": 0}]}}, DUBLIN)


@pytest.mark.parametrize("now, slot", [
    ("2026-06-15T12:03:10", "06-15 12:00:00"),
    ("2026-06-15T12:05:00", "06-15 12:05:00"),     # a slot is its own latest
    ("2026-06-15T01:20:00", "06-15 01:00:00"),     # the night range: on the half hour
    ("2026-06-15T07:03:00", "06-15 07:00:00"),
    ("2026-06-15T06:59:00", "06-15 06:30:00"),
])
def test_the_latest_slot_at_or_before_a_time(now, slot):
    assert datetime.fromtimestamp(clock().slot_before(at(now)), DUBLIN).strftime(
        "%m-%d %H:%M:%S") == slot


@pytest.mark.parametrize("t, inside", [
    ("00:30", False), ("01:00", True), ("06:59", True), ("07:00", False), ("12:00", False),
])
def test_a_window_runs_from_its_start_up_to_its_end(t, inside):
    assert in_window(parse_hhmm(t), parse_hhmm("01:00"), parse_hhmm("07:00")) is inside


def test_a_window_past_midnight():
    start, end = parse_hhmm("23:00"), parse_hhmm("07:00")
    assert in_window(parse_hhmm("23:30"), start, end)
    assert in_window(parse_hhmm("03:00"), start, end)
    assert not in_window(parse_hhmm("07:00"), start, end)
    assert not in_window(parse_hhmm("12:00"), start, end)
