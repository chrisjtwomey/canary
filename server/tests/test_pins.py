"""The places this repo names an epd version must agree.

``server/requirements.txt`` pins the server core, from PyPI. ``platformio.ini``
pins the firmware's libraries, from the PlatformIO registry. Both sides
implement one contract — the ``EPD-Next-*`` headers — so a bump that moves only
one of them builds the firmware against a library the server has outgrown.
"""
from __future__ import annotations

import configparser
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLATFORMIO = ROOT / "platformio.ini"
REQUIREMENTS = ROOT / "server" / "requirements.txt"


def _requirements_epd_pin() -> str:
    """The release requirements.txt pins epd-server to."""
    pin = re.search(r"^epd-server==(\S+)$", REQUIREMENTS.read_text(), re.MULTILINE)
    assert pin, "requirements.txt no longer pins epd-server to a release"
    return pin.group(1)


def _firmware_epd_pins() -> dict[str, str]:
    """The release platformio.ini pins each epd library to, by library."""
    ini = configparser.ConfigParser(interpolation=None)
    ini.read(PLATFORMIO)
    pins = {}
    for key in ("client", "inkplate"):
        name, _, version = ini["kit"][key].partition(" @ ")
        pins[name] = version
    return pins


def test_the_firmware_and_the_server_pin_the_same_epd():
    assert _firmware_epd_pins() == {
        "chrisjtwomey/EpdClient": _requirements_epd_pin(),
        "chrisjtwomey/EpdBoardInkplate": _requirements_epd_pin(),
    }


def test_a_board_environment_takes_epd_from_the_registry_and_its_dev_twin_from_a_checkout():
    ini = configparser.ConfigParser(interpolation=None)
    ini.read(PLATFORMIO)

    for board in ("esp32", "dock"):
        assert "symlink://" not in ini[f"env:{board}"]["lib_deps"]
        assert "${kit.client}" in ini[f"env:{board}"]["lib_deps"]
        assert ini[f"env:{board}-dev"]["extends"] == f"env:{board}"
        assert "symlink://../epd/firmware" in ini[f"env:{board}-dev"]["lib_deps"]
