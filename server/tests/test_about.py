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

    assert About("v1.0.0", settings).answer({})["firmware"] is None


def test_it_names_the_image_on_offer(tmp_path):
    (tmp_path / "v1.6.0.bin").write_bytes(b"\xe9firmware")
    settings = FirmwareSettings(enabled=True, dir=str(tmp_path), product="canary-head",
                                offer_dev_builds=False)

    assert About("v1.0.0", settings).answer({})["firmware"] == {
        "product": "canary-head", "version": "v1.6.0"}


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
