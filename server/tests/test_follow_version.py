"""A server offers development builds exactly when it runs one."""
import pytest
from epd_server.config import FirmwareSettings

from server import follow_own_version


@pytest.mark.parametrize("version, offered", [
    ("v0.3.1", False),                     # a tagged server: releases only
    ("v0.3.1-3-g3530079", True),           # a server past a tag: its builder's builds
    ("v0.3.1-3-g3530079-dirty", True),
    ("dev", True),
])
def test_development_builds_follow_the_servers_own_version(version, offered):
    firmware = FirmwareSettings(enabled=True, dir="firmware", product="canary-head",
                                offer_dev_builds=not offered)
    assert follow_own_version(firmware, version).offer_dev_builds is offered
