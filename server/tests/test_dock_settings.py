"""GET /board-settings: the dock's settings from config.yaml, the light's
quiet hours, and a recalibration waiting to run."""
from datetime import datetime

import pytest
from epd_server.config import ConfigError

from dock_settings import (DOCK, RECALIBRATE_WITHIN_S, BoardSettings, DockSettings,
                           load_dock_settings)
from schedule import PostSchedule, parse_hhmm
from server import check_config
from sources.calibration import CalibrationStore
from tests.conftest import TZ


def at(hour, minute):
    return datetime(2026, 9, 23, hour, minute, tzinfo=TZ).timestamp()


POSTS = PostSchedule(300, TZ, parse_hhmm("01:00"), parse_hhmm("07:00"), 1800)


@pytest.fixture
def requests(tmp_path):
    store = CalibrationStore(tmp_path / "calibration.db")
    yield store
    store.close()


def board(settings=DockSettings(), requests=None, report=None, now=at(12, 0)):
    return BoardSettings(settings, POSTS, requests, lambda device: report,
                         now=lambda: now)


def report(offline=False, age_s=60, **client):
    return {"doc": {"ts": 1, "device": DOCK, "client": client}, "age_s": age_s,
            "offline": offline}


def test_a_config_without_a_dock_block_gives_the_defaults():
    assert load_dock_settings({}) == DockSettings(
        pm_warmup_s=35, scd41_temperature_offset_c=4.0, scd41_self_calibration=True,
        shtc3_low_power=False, led_brightness_pct=15, led_off_in_quiet_hours=False,
        log_level="debug", bsec_sample_s=300)


def test_it_reads_each_key_of_the_dock_block():
    settings = load_dock_settings({"dock": {
        "pm": {"warmup_s": 0},
        "scd41": {"temperature_offset_c": 2.5, "self_calibration": False},
        "shtc3": {"low_power": True},
        "led": {"brightness_pct": 40, "off_in_quiet_hours": True},
        "log": {"level": "info"},
        "bsec": {"sample_s": 3}}})

    assert settings == DockSettings(0, 2.5, False, True, 40, True, "info", 3)


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
])
def test_a_value_out_of_range_is_refused_by_its_key(block, key):
    with pytest.raises(ConfigError, match=f"^{key} "):
        load_dock_settings({"dock": block})


def test_the_server_will_not_start_on_a_bad_dock_block():
    with pytest.raises(ValueError, match="dock.pm.warmup_s"):
        check_config("dock:\n  pm:\n    warmup_s: 5\n")


def test_the_version_changes_with_any_setting_and_only_then():
    base = DockSettings()

    assert DockSettings().version == base.version
    assert DockSettings(led_brightness_pct=16).version != base.version
    assert DockSettings(log_level="info").version != base.version


def test_the_light_in_quiet_hours_is_not_part_of_the_version():
    """It is a choice of when, which the answer carries as dark."""
    assert DockSettings(led_off_in_quiet_hours=True).version == DockSettings().version


def test_the_answer_is_the_settings_and_their_version(requests):
    answer = board(requests=requests).answer({"device": DOCK})

    assert answer == {
        "version": DockSettings().version,
        "pm": {"warmup_s": 35},
        "scd41": {"temperature_offset_c": 4.0, "self_calibration": True},
        "shtc3": {"low_power": False},
        "led": {"brightness_pct": 15, "dark": False},
        "log": {"level": "debug"},
        "bsec": {"sample_s": 300},
    }


@pytest.mark.parametrize("args", [{}, {"device": "canary-head"}])
def test_only_the_dock_has_settings(args, requests):
    with pytest.raises(ValueError):
        board(requests=requests).answer(args)


@pytest.mark.parametrize("now, dark", [
    (at(0, 50), False),     # next slot 00:55
    (at(0, 56), True),      # next slot 01:00, in quiet hours
    (at(6, 45), False),     # next slot 07:00, out of them
    (at(3, 10), True),
])
def test_the_light_is_dark_before_a_slot_in_quiet_hours(now, dark, requests):
    settings = DockSettings(led_off_in_quiet_hours=True)

    assert board(settings, requests, now=now).answer({"device": DOCK})["led"]["dark"] is dark


def test_the_light_stays_on_in_quiet_hours_unless_asked(requests):
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
    (at(1, 20), 25 * 60),       # 01:00, the first quiet slot, and 00:55 before it
    (at(1, 40), 40 * 60),       # quiet: 01:30 and 01:00
    (at(7, 3), 33 * 60),        # 07:00 and 06:30
])
def test_the_dock_may_be_silent_until_two_slots_are_missed(now, silence):
    from server import make_silence
    assert make_silence(POSTS)("canary-dock", now) == silence
    assert make_silence(POSTS)("canary-head", now) == 120


def test_a_recalibration_past_the_hour_and_not_run_has_expired(requests):
    board(requests=requests, now=at(12, 0)).recalibrate(420)

    assert board(requests=requests, now=at(12, 30)).expired() is None
    assert board(requests=requests, now=at(13, 1)).expired() == {"id": int(at(12, 0)), "ppm": 420}
    ran = report(recalibrated={"id": int(at(12, 0)), "ppm": 420, "ok": True})
    assert board(requests=requests, now=at(13, 1), report=ran).expired() is None


@pytest.mark.parametrize("now, slot", [(at(12, 3), "12:05"), (at(1, 10), "01:30")])
def test_the_next_report_is_the_next_slot_in_local_time(now, slot, requests):
    assert board(requests=requests, now=now).next_report() == slot
