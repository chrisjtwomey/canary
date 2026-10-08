"""setup.py and setup.sh: the first start from a terminal."""
import os
import subprocess

import pytest

import config_form as cf
import setup
from server import check_config

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE = open(os.path.join(HERE, "..", "config.example.yaml")).read()
SETUP_SH = os.path.join(HERE, "..", "..", "setup.sh")


def test_the_first_config_is_set_for_a_real_install_and_keeps_the_examples_comments():
    text = setup.first_config(EXAMPLE, "America/New_York", "http://roci.local:8080")

    cfg = cf.read(text)
    assert cfg["source"]["kind"] == "store"
    assert cfg["client"]["firmware"]["enabled"] is True
    assert cfg["server"]["timezone"] == "America/New_York"
    assert cfg["client"]["server_url"] == "http://roci.local:8080"
    assert "# what the board runs, not what this server does" in text
    check_config(text)


def test_a_time_zone_the_image_does_not_know_leaves_the_examples():
    text = setup.first_config(EXAMPLE, "Mars/Olympus", "")

    assert cf.read(text)["server"]["timezone"] == cf.read(EXAMPLE)["server"]["timezone"]


@pytest.fixture
def owned(monkeypatch):
    """The paths handed to the containers' user, without needing root."""
    paths = []
    monkeypatch.setattr(setup.os, "chown", lambda path, uid, gid: paths.append((path, uid, gid)))
    return paths


def test_a_first_run_writes_the_config_and_makes_the_firmware_folder(tmp_path, owned):
    said = setup.set_up(str(tmp_path), "Europe/Dublin", "http://roci.local:8080")

    assert said == ["Wrote server/config.yaml: your readings, firmware updates on, "
                    "time zone Europe/Dublin."]
    assert (tmp_path / "firmware").is_dir()
    assert owned == [(str(tmp_path / "config.yaml"), 1000, 1000),
                     (str(tmp_path / "firmware"), 1000, 1000)]


def test_a_config_that_exists_is_kept(tmp_path, owned):
    (tmp_path / "config.yaml").write_text("debug: true\n")

    said = setup.set_up(str(tmp_path), "Europe/Dublin", "http://roci.local:8080")

    assert said == ["Kept server/config.yaml: it exists already."]
    assert (tmp_path / "config.yaml").read_text() == "debug: true\n"


def test_the_empty_folder_docker_made_in_the_configs_place_is_replaced(tmp_path, owned):
    (tmp_path / "config.yaml").mkdir()

    said = setup.set_up(str(tmp_path), "Europe/Dublin", "")

    assert said[0] == "Replaced the empty server/config.yaml folder that Docker made."
    assert said[1].startswith("Wrote server/config.yaml")
    assert (tmp_path / "config.yaml").is_file()


FAKE_DOCKER = """#!/bin/sh
printf '%s\\n' "$*" >> "$CALLS"
"""


def run_setup_sh(tmp_path, docker=FAKE_DOCKER):
    fake = tmp_path / "bin"
    fake.mkdir()
    if docker is not None:
        (fake / "docker").write_text(docker)
        (fake / "docker").chmod(0o755)
    calls = tmp_path / "calls"
    path = f"{fake}:/usr/bin:/bin:/usr/sbin:/sbin"
    result = subprocess.run(["sh", SETUP_SH], env={"PATH": path, "CALLS": str(calls)},
                            capture_output=True, text=True, timeout=30)
    return result, calls.read_text().splitlines() if calls.exists() else []


def local_name() -> str:
    """This computer's mDNS name, as setup.sh finds it."""
    for command in (["/usr/sbin/scutil", "--get", "LocalHostName"], ["hostname", "-s"]):
        try:
            found = subprocess.run(command, capture_output=True, text=True)
        except FileNotFoundError:
            continue
        if found.returncode == 0:
            return found.stdout.strip()
    raise AssertionError("no host name")


def test_setup_sh_runs_the_setup_service_then_starts_the_stack(tmp_path):
    host = local_name()

    result, calls = run_setup_sh(tmp_path)

    assert result.returncode == 0, result.stderr
    assert calls[0] == "compose version"
    assert calls[1].startswith("compose run --rm -e SETUP_TIMEZONE=")
    assert calls[1].endswith(f"-e SETUP_SERVER_URL=http://{host}.local:8080 setup")
    assert calls[2] == "compose up -d"
    assert result.stdout.splitlines()[-4:] == [
        "Canary is running.",
        f"Install the boards: https://{host}.local:8443/web/install",
        "Your browser warns about the certificate first. Select Advanced, then continue.",
        "The first firmware build takes some minutes. To follow it: "
        "docker compose logs -f firmware-builder",
    ]


def test_setup_sh_without_docker_says_what_to_do(tmp_path):
    result, calls = run_setup_sh(tmp_path, docker="#!/bin/sh\nexit 1\n")

    assert result.returncode == 1
    assert result.stderr.strip() == "Docker Compose not found. Install Docker, then try again."
