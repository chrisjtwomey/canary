"""Each board's sync schedule and the page schedule, as the server reads
them from config.yaml. epd's tests cover how a day of time ranges works."""
from zoneinfo import ZoneInfo

import pytest
from epd_server.config import ConfigError

from server import load_settings, make_dock_sync, make_head_sync

DUBLIN = ZoneInfo("Europe/Dublin")
POOLS = {"co2": ["breathe.png"]}


def test_config_without_a_schedule_keeps_the_slower_night():
    assert make_dock_sync({}, DUBLIN).describe() == [{"from": "01:00", "every": 1800},
                                                     {"from": "07:00", "every": 300}]


def test_config_can_set_the_ranges():
    sync = make_dock_sync({"dock": {"sync": [{"from": "23:00", "every": 3600},
                                             {"from": "06:00", "every": 600}]}}, DUBLIN)
    assert sync.describe() == [{"from": "06:00", "every": 600}, {"from": "23:00", "every": 3600}]


def test_the_dock_must_sync_in_some_range():
    with pytest.raises(ConfigError, match="^dock.sync has no range that syncs"):
        make_dock_sync({"dock": {"sync": [{"from": "00:00", "every": 0}]}}, DUBLIN)


def test_config_without_a_head_schedule_syncs_the_head_every_half_hour_all_day():
    assert make_head_sync({}, DUBLIN).describe() == [{"from": "00:00", "every": 1800}]


def test_the_head_syncs_every_so_often_all_day():
    sync = make_head_sync({"head": {"sync": {"every": 600}}}, DUBLIN)
    assert sync.describe() == [{"from": "00:00", "every": 600}]


def test_a_head_that_syncs_only_beside_its_pages_has_no_slots():
    off = make_head_sync({"head": {"sync": {"every": 0}}}, DUBLIN)
    assert off.seconds_until_next(1_781_000_000) is None


@pytest.mark.parametrize("block, words", [
    ({"every": 45}, "^head.sync.every must be 0, for off, or a whole number of minutes"),
    ({"every": "1800"}, "^head.sync.every must be"),
    ([{"from": "00:00", "every": 1800}], "^head.sync must be {every: seconds}"),
    ({"every": 1800, "from": "07:00"}, "^head.sync must be {every: seconds}"),
])
def test_a_head_sync_that_cannot_work_is_refused_by_its_key(block, words):
    with pytest.raises(ConfigError, match=words):
        make_head_sync({"head": {"sync": block}}, DUBLIN)


def test_the_page_changes_on_time_ranges():
    settings = load_settings({"display": {"pools": POOLS, "schedule": {
        "type": "timeranges", "ranges": [{"from": "07:00", "every": 300},
                                         {"from": "23:00", "every": 0}]}}})
    assert settings.core.server.schedule.describe()["ranges"] == [
        {"from": "07:00", "every": 300}, {"from": "23:00", "every": 0}]


def test_config_without_a_display_block_changes_the_page_every_hour():
    assert load_settings({}).core.server.schedule.describe()["ranges"] == [
        {"from": "00:00", "every": 3600}]


def test_a_page_schedule_of_set_times_is_refused():
    with pytest.raises(ConfigError, match="^display.schedule.type must be timeranges"):
        load_settings({"display": {"pools": POOLS,
                                   "schedule": {"type": "times", "08:00:00": "co2"}}})
