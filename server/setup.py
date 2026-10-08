"""First start: server/config.yaml from the example, set for a real install,
and server/firmware, both owned by the user the containers run as.

setup.sh runs this as root in docker-compose.yml's setup service, with the
host's server folder at the path it is given, so the host needs no sudo. A
config that exists is kept, so it can run again at any time.
"""
from __future__ import annotations

import os
import sys
import zoneinfo

import config_form as cf

# The user the containers run as (docker-compose.yml).
OWNER = 1000
HERE = os.path.dirname(os.path.abspath(__file__))


def first_config(example: str, timezone: str, server_url: str) -> str:
    """The example config, set for a real install: the readings the dock posts,
    the images the builder makes, and the host's time zone and address. A time
    zone this image does not know leaves the example's."""
    doc = cf.Doc(example)
    doc.set(("source", "kind"), "store")
    doc.set(("client", "firmware", "enabled"), True)
    try:
        zoneinfo.ZoneInfo(timezone)
    except (ValueError, zoneinfo.ZoneInfoNotFoundError):
        timezone = ""
    if timezone:
        doc.set(("server", "timezone"), timezone)
    if server_url:
        doc.set(("client", "server_url"), server_url)
    return doc.text()


def set_up(folder: str, timezone: str, server_url: str) -> list[str]:
    """Writes ``folder``/config.yaml unless it exists, makes ``folder``/firmware,
    and hands both to the containers' user. Returns what it did, as lines for
    the person who ran it."""
    said = []
    config = os.path.join(folder, "config.yaml")
    if os.path.isdir(config) and not os.listdir(config):
        os.rmdir(config)
        said.append("Replaced the empty server/config.yaml folder that Docker made.")
    if os.path.exists(config):
        said.append("Kept server/config.yaml: it exists already.")
    else:
        with open(os.path.join(HERE, "config.example.yaml")) as f:
            text = first_config(f.read(), timezone, server_url)
        with open(config, "w") as f:
            f.write(text)
        zone = cf.read(text)["server"]["timezone"]
        said.append(f"Wrote server/config.yaml: your readings, firmware updates on, time zone {zone}.")
    firmware = os.path.join(folder, "firmware")
    os.makedirs(firmware, exist_ok=True)
    for path in (config, firmware):
        os.chown(path, OWNER, OWNER)
    return said


if __name__ == "__main__":
    for line in set_up(sys.argv[1], os.environ.get("SETUP_TIMEZONE", ""),
                       os.environ.get("SETUP_SERVER_URL", "")):
        print(line)
