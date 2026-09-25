"""GET /board-settings: the dock's settings from config.yaml, the light's
schedule, and a recalibration waiting to run."""
from datetime import datetime

import pytest
from epd_server.config import ConfigError

from dock_settings import (DOCK, RECALIBRATE_WITHIN_S, BoardSettings, DockSettings,
                           load_dock_settings)
from epd_server.timeranges import TimeRanges, parse_hhmm
from server import check_config
from sources.calibration import CalibrationStore
from tests.conftest import TZ


def at(hour, minute):
    return datetime(2026, 9, 23, hour, minute, tzinfo=TZ).timestamp()


SYNC = TimeRanges([(parse_hhmm("07:00"), 300), (parse_hhmm("01:00"), 1800)], TZ, "dock.sync")
DAY = (parse_hhmm("07:00"), parse_hhmm("01:00"))


@pytest.fixture
def requests(tmp_path):
    store = CalibrationStore(tmp_path / "calibration.db")
    yield store
    store.close()


def board(settings=DockSettings(), requests=None, report=None, now=at(12, 0)):
    return BoardSettings(settings, SYNC, requests, lambda device: report,
                         now=lambda: now)


def report(offline=False, age_s=60, **client):
    return {"doc": {"ts": 1, "device": DOCK, "client": {"dock": client}}, "age_s": age_s,
            "offline": offline}


def test_a_config_without_a_dock_block_gives_the_defaults():
    assert load_dock_settings({}) == DockSettings(
        pm_warmup_s=35, scd41_temperature_offset_c=4.0, scd41_self_calibration=True,
        shtc3_low_power=False, led_brightness_pct=15, led_schedule=None,
        log_level="debug", bsec_sample_s=300, led_looks=(
            ("starting", "pulse", 0.5), ("no_wifi", "flash", 1.0), ("post_failed", "flash", 2.0),
            ("sensor_missing", "flash", 3.0), ("well", "pulse", 1.0)))


def test_it_reads_each_key_of_the_dock_block():
    settings = load_dock_settings({"dock": {
        "pm": {"warmup_s": 0},
        "scd41": {"temperature_offset_c": 2.5, "self_calibration": False},
        "shtc3": {"low_power": True},
        "led": {"brightness_pct": 40, "schedule": {"from": "07:00", "to": "01:00"}},
        "log": {"level": "info"},
        "bsec": {"sample_s": 3}}})

    assert settings == DockSettings(0, 2.5, False, True, 40, DAY, "info", 3)


@pytest.mark.parametrize("block, key", [
    ({"pm": {"warmup_s": 10}}, "dock.pm.warmup_s"),
    ({"pm": {"warmup_s": 601}}, "dock.pm.warmup_s"),
    ({"scd41": {"temperature_offset_c": 21}}, "dock.scd41.temperature_offset_c"),
    ({"scd41": {"temperature_offset_c": -1}}, "dock.scd41.temperature_offset_c"),
    ({"scd41": {"self_calibration": "yes"}}, "dock.scd41.self_calibration"),
    ({"led": {"brightness_pct": 101}}, "dock.led.brightness_pct"),
    ({"log": {"level": "verbose"}}, "dock.log.level"),
    ({"bsec": {"sample_s": 60}}, "dock.bsec.sample_s"),
    ({"bsec": {"sample_s": "300"}}, "dock.bsec.sample_s"),
    ({"led": {"schedule": {"from": "07:00"}}}, "dock.led.schedule"),
    ({"led": {"schedule": {"from": "25:00", "to": "01:00"}}}, "dock.led.schedule:"),
    ({"led": {"schedule": {"from": "07:00", "to": "07:00"}}}, "dock.led.schedule"),
    ({"led": {"schedule": True}}, "dock.led.schedule"),
])
def test_a_value_out_of_range_is_refused_by_its_key(block, key):
    with pytest.raises(ConfigError, match=f"^{key} "):
        load_dock_settings({"dock": block})


def looks(*given):
    return load_dock_settings({"dock": {"led": {"looks": list(given)}}}).led_looks


def test_the_looks_are_the_ones_given_in_the_triggers_order():
    assert looks({"trigger": "well", "pattern": "solid", "length_s": 2},
                 {"trigger": "no_wifi", "pattern": "flash", "length_s": 0.25}) \
        == (("no_wifi", "flash", 0.25), ("well", "solid", 2.0))


def test_off_and_solid_need_no_length():
    assert looks({"trigger": "well", "pattern": "solid"},
                 {"trigger": "starting", "pattern": "off"}) \
        == (("starting", "off", 1.0), ("well", "solid", 1.0))


def test_a_double_or_a_triple_is_a_look_like_the_rest():
    assert looks({"trigger": "well", "pattern": "triple_flash", "length_s": 1.9},
                 {"trigger": "no_wifi", "pattern": "double_pulse", "length_s": 0.9}) \
        == (("no_wifi", "double_pulse", 0.9), ("well", "triple_flash", 1.9))


def test_no_looks_is_a_light_that_shows_nothing_but_an_update():
    assert looks() == ()


@pytest.mark.parametrize("value, words", [
    ({"well": {"pattern": "pulse"}}, "must be a list of looks"),
    ([["well", "pulse", 1]], "must be a list of looks"),
    ([{"trigger": "well"}], "each look has trigger, pattern and length_s, not trigger"),
    ([{"trigger": "well", "pattern": "pulse", "every": 1}], "each look has"),
    ([{"trigger": "wifi", "pattern": "pulse"}], "trigger must be one of starting, no_wifi, "
                                                "post_failed, sensor_missing, well, not 'wifi'"),
    ([{"trigger": "well", "pattern": "off"}, {"trigger": "well", "pattern": "solid"}],
     "has two looks for well"),
    ([{"trigger": "well", "pattern": "blink"}], "well's pattern must be one of off, solid, pulse, "
                                                "double_pulse, triple_pulse, flash, double_flash, "
                                                "triple_flash, not 'blink'"),
    ([{"trigger": "well", "pattern": "pulse"}], "well's pulse needs a length_s"),
    ([{"trigger": "well", "pattern": "pulse", "length_s": 0.2}], "well's length_s must be "
                                                                  "from 0.25 to 10 for pulse, "
                                                                  "not 0.2"),
    ([{"trigger": "well", "pattern": "double_flash", "length_s": 0.8}],
     "well's length_s must be from 0.9 to 10 for double_flash, not 0.8"),
    ([{"trigger": "well", "pattern": "triple_pulse", "length_s": 1.1}],
     "well's length_s must be from 1.2 to 10 for triple_pulse, not 1.1"),
    ([{"trigger": "well", "pattern": "pulse", "length_s": 11}], "well's length_s"),
    ([{"trigger": "well", "pattern": "pulse", "length_s": True}], "well's length_s"),
])
def test_looks_that_cannot_work_are_refused_by_their_key(value, words):
    with pytest.raises(ConfigError, match="^dock.led.looks") as caught:
        load_dock_settings({"dock": {"led": {"looks": value}}})
    assert words in str(caught.value)


def test_a_look_is_part_of_the_version():
    assert DockSettings(led_looks=(("well", "off", 1.0),)).version != DockSettings().version


def test_the_server_will_not_start_on_a_bad_dock_block():
    with pytest.raises(ValueError, match="dock.pm.warmup_s"):
        check_config("dock:\n  pm:\n    warmup_s: 5\n")


def test_the_version_changes_with_any_setting_and_only_then():
    base = DockSettings()

    assert DockSettings().version == base.version
    assert DockSettings(led_brightness_pct=16).version != base.version
    assert DockSettings(log_level="info").version != base.version


def test_the_lights_schedule_is_not_part_of_the_version():
    """It is a choice of when, which the answer carries as dark."""
    assert DockSettings(led_schedule=DAY).version == DockSettings().version


def test_a_schedule_given_as_nothing_is_all_day():
    assert load_dock_settings({"dock": {"led": {"schedule": {}}}}).led_schedule is None


def test_the_answer_is_the_settings_and_their_version(requests):
    answer = board(requests=requests).answer({"device": DOCK})

    assert answer == {
        "version": DockSettings().version,
        "pm": {"warmup_s": 35},
        "scd41": {"temperature_offset_c": 4.0, "self_calibration": True},
        "shtc3": {"low_power": False},
        "led": {"brightness_pct": 15, "dark": False, "looks": [
            {"trigger": "starting", "pattern": "pulse", "length_s": 0.5},
            {"trigger": "no_wifi", "pattern": "flash", "length_s": 1},
            {"trigger": "post_failed", "pattern": "flash", "length_s": 2},
            {"trigger": "sensor_missing", "pattern": "flash", "length_s": 3},
            {"trigger": "well", "pattern": "pulse", "length_s": 1}]},
        "log": {"level": "debug"},
        "bsec": {"sample_s": 300},
    }


@pytest.mark.parametrize("args", [{}, {"device": "canary-head"}])
def test_only_the_dock_has_settings(args, requests):
    with pytest.raises(ValueError):
        board(requests=requests).answer(args)


@pytest.mark.parametrize("now, dark", [
    (at(0, 50), False),     # next slot 00:55
    (at(0, 56), True),      # next slot 01:00, past the schedule
    (at(6, 45), False),     # next slot 07:00, out of them
    (at(3, 10), True),
])
def test_the_light_is_dark_before_a_slot_outside_its_schedule(now, dark, requests):
    settings = DockSettings(led_schedule=DAY)

    assert board(settings, requests, now=now).answer({"device": DOCK})["led"]["dark"] is dark


def test_the_light_is_on_all_day_without_a_schedule(requests):
    assert board(requests=requests, now=at(3, 10)).answer({"device": DOCK})["led"]["dark"] is False


def test_a_recalibration_waits_in_the_answer_until_the_dock_reports_it(requests):
    asked = board(requests=requests, now=at(12, 0))
    request_id = asked.recalibrate("420")

    waiting = board(requests=requests, now=at(12, 3)).answer({"device": DOCK})
    done = board(requests=requests, now=at(12, 6),
                 report=report(recalibrated={"id": request_id, "ppm": 420, "ok": True,
                                             "correction_ppm": -12}))

    assert waiting["recalibrate"] == {"id": int(at(12, 0)), "ppm": 420}
    assert "recalibrate" not in done.answer({"device": DOCK})
    assert done.last_recalibration()["correction_ppm"] == -12


def test_a_recalibration_the_dock_has_not_run_within_the_hour_is_dropped(requests):
    board(requests=requests, now=at(12, 0)).recalibrate(420)
    late = board(requests=requests, now=at(12, 0) + RECALIBRATE_WITHIN_S + 1)

    assert "recalibrate" not in late.answer({"device": DOCK})


def test_a_second_request_replaces_the_first(requests):
    board(requests=requests, now=at(12, 0)).recalibrate(420)
    board(requests=requests, now=at(12, 0)).recalibrate(450)

    pending = board(requests=requests, now=at(12, 1)).pending()

    assert pending == {"id": int(at(12, 0)) + 1, "ppm": 450}


@pytest.mark.parametrize("ppm", ["399", "2001", "four hundred", ""])
def test_a_reference_out_of_range_is_refused(ppm, requests):
    with pytest.raises(ValueError, match="^Enter "):
        board(requests=requests).recalibrate(ppm)
    assert board(requests=requests).pending() is None


@pytest.mark.parametrize("client, applied", [
    ({}, (None, [])),
    ({"settings": {"version": DockSettings().version}}, (True, [])),
    ({"settings": {"version": "00000000"}}, (False, [])),
    ({"settings": {"version": DockSettings().version, "refused": ["pm.warmup_s"]}},
     (True, ["pm.warmup_s"])),
])
def test_it_says_whether_the_dock_runs_these_settings(client, applied, requests):
    assert board(requests=requests, report=report(**client)).applied() == applied


def test_the_dock_is_offline_as_its_reports_say(requests):
    assert board(requests=requests).offline() == (False, None)
    assert board(requests=requests, report=report(age_s=60)).offline() == (False, 60)
    assert board(requests=requests, report=report(offline=True, age_s=900)).offline() == (True, 900)


@pytest.mark.parametrize("now, silence", [
    (at(12, 3), 8 * 60),        # slots 12:00 and 11:55: two missed by 12:03 means none since 11:55
    (at(1, 20), 25 * 60),       # 01:00, the night range's first slot, and 00:55 before it
    (at(1, 40), 40 * 60),       # the night range: 01:30 and 01:00
    (at(7, 3), 33 * 60),        # 07:00 and 06:30
])
def test_the_dock_may_be_silent_until_two_slots_are_missed(now, silence):
    from server import make_silence
    assert make_silence({"canary-dock": SYNC})("canary-dock", now) == silence


def test_a_range_that_is_off_lengthens_the_silence_the_dock_may_keep():
    from server import make_silence
    off_at_night = TimeRanges([(parse_hhmm("07:00"), 300), (parse_hhmm("22:00"), 0)], TZ,
                                 "dock.sync")
    # The last two slots before 03:00 are 21:55 and 21:50.
    assert make_silence({"canary-dock": off_at_night})("canary-dock", at(3, 0)) == \
        5 * 3600 + 10 * 60


def test_each_board_has_its_own_next_sync_and_an_unknown_one_none():
    from server import make_next_sync
    head = TimeRanges([(parse_hhmm("00:00"), 1800)], TZ, "head.sync")
    now = at(12, 3)
    syncs = {"canary-dock": SYNC, "canary-head": head}
    assert make_next_sync(syncs)("canary-dock", now) == 2 * 60
    assert make_next_sync(syncs)("canary-head", now) == 27 * 60
    assert make_next_sync(syncs)("weather-cal", now) is None


def test_each_board_is_sent_its_own_next_sync_and_an_unnamed_one_none():
    from server import make_sensor_poll
    head = TimeRanges([(parse_hhmm("00:00"), 1800)], TZ, "head.sync")
    poll = make_sensor_poll({"canary-dock": SYNC, "canary-head": head})
    assert poll(at(12, 3), "canary-dock") == 2 * 60
    assert poll(at(12, 3), "canary-head") == 27 * 60
    assert poll(at(12, 3), None) is None


def test_the_head_is_offline_after_two_of_its_own_syncs():
    from server import make_silence
    head = TimeRanges([(parse_hhmm("00:00"), 1800)], TZ, "head.sync")
    # Slots 12:00 and 11:30: at 12:10 the head may have been silent since 11:30.
    assert make_silence({"canary-head": head})("canary-head", at(12, 10)) == 40 * 60


def test_a_board_with_no_slot_is_never_judged():
    from server import make_silence
    off = TimeRanges([(parse_hhmm("00:00"), 0)], TZ, "head.sync")
    assert make_silence({"canary-head": off})("canary-head", at(12, 10)) == float("inf")
    assert make_silence({})("canary-head", at(12, 10)) == float("inf")


def test_a_recalibration_past_the_hour_and_not_run_has_expired(requests):
    board(requests=requests, now=at(12, 0)).recalibrate(420)

    assert board(requests=requests, now=at(12, 30)).expired() is None
    assert board(requests=requests, now=at(13, 1)).expired() == {"id": int(at(12, 0)), "ppm": 420}
    ran = report(recalibrated={"id": int(at(12, 0)), "ppm": 420, "ok": True})
    assert board(requests=requests, now=at(13, 1), report=ran).expired() is None


@pytest.mark.parametrize("now, slot", [(at(12, 3), "12:05"), (at(1, 10), "01:30")])
def test_the_next_sync_is_the_next_slot_in_local_time(now, slot, requests):
    assert board(requests=requests, now=now).next_sync() == slot
