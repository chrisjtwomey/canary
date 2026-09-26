"""GET /about: the server's own version, clock and firmware offer."""
import os

import pytest
from epd_server import __version__ as library_version
from epd_server.config import FirmwareSettings

from about import About
from version import server_version


def at(seconds):
    return lambda: seconds


def test_it_reports_the_version_it_was_given_and_the_library_it_uses():
    answer = About("canary-v2.0.0", now=at(1_700_000_000)).answer({})

    assert answer["server"] == {"version": "canary-v2.0.0",
                                "library": library_version,
                                "epoch": 1_700_000_000}


def test_a_server_with_no_firmware_says_so():
    assert About("v1.0.0").answer({})["firmware"] is None


def test_a_firmware_directory_with_no_image_offers_nothing(tmp_path):
    settings = FirmwareSettings(enabled=True, dir=str(tmp_path), product="canary-head",
                                offer_dev_builds=False)

    assert About("v1.0.0", settings).answer({})["firmware"] == {"canary-head": None}


def test_it_names_the_image_each_board_is_offered(tmp_path):
    """The newest each product has that can work with the server, which is v1.0.0."""
    for product, version in (("canary-head", "v1.6.0"), ("canary-head", "v2.0.0"),
                             ("canary-dock", "v2.1.0")):
        (tmp_path / product).mkdir(exist_ok=True)
        (tmp_path / product / f"{version}.bin").write_bytes(b"\xe9firmware")
    settings = FirmwareSettings(enabled=True, dir=str(tmp_path), product="canary-head",
                                offer_dev_builds=False, products=("canary-head", "canary-dock"))

    assert About("v1.0.0", settings).answer({})["firmware"] == {
        "canary-head": "v1.6.0", "canary-dock": None}


def test_the_build_stamps_the_version(monkeypatch):
    monkeypatch.setenv("CANARY_VERSION", "v9.9.9")

    assert server_version() == "v9.9.9"


def test_an_unstamped_build_falls_back_to_the_checkout(monkeypatch):
    monkeypatch.delenv("CANARY_VERSION", raising=False)

    described = server_version()

    assert described == "dev" or described.startswith("v")


def test_a_blank_stamp_is_not_a_version(monkeypatch):
    monkeypatch.setenv("CANARY_VERSION", "   ")

    assert server_version() != "   "


def test_it_gives_each_boards_sync_week_and_next_slot():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from epd_server.timeranges import TimeRanges, Week, parse_hhmm
    tz = ZoneInfo("Europe/Dublin")
    now = datetime(2026, 6, 15, 12, 3, 10, tzinfo=tz).timestamp()
    sync = Week.every_day(TimeRanges([(parse_hhmm("07:00"), 300), (parse_hhmm("22:00"), 0)], tz))
    head = Week.every_day(TimeRanges([(parse_hhmm("00:00"), 1800)], tz))
    answer = About("v1.0.0", now=at(now), syncs={"dock": sync, "head": head}).answer({})

    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    assert answer["sync"] == {
        "dock": {"week": [{"days": days, "ranges": [{"from": "07:00", "every": 300},
                                                    {"from": "22:00", "every": 0}]}],
                 "next_s": 110},
        "head": {"week": [{"days": days, "ranges": [{"from": "00:00", "every": 1800}]}],
                 "next_s": 1610}}
    assert About("v1.0.0").answer({})["sync"] is None
