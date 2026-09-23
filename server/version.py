"""What this server calls itself.

The version goes out on every response and in ``GET /about``, so a board can
tell whether it and the server speak the same contract. It is canary's own,
not the ``epd-server`` package's: the package is a library this server is
built with, and the two move independently.

The image is built with ``CANARY_VERSION`` set by CI: the release tag for a
release, and ``git describe`` for a push to main. A checkout run by hand asks
git instead, the way ``scripts/version.py`` does for the firmware. Neither answering leaves ``dev``, which never matches
a board and so is never mistaken for a release.
"""
from __future__ import annotations

import os
import subprocess


def server_version() -> str:
    """This server's version: the build's, else the checkout's, else "dev"."""
    stamped = os.environ.get("CANARY_VERSION", "").strip()
    if stamped:
        return stamped
    return _git_version()


def _git_version() -> str:
    try:
        described = subprocess.check_output(
            ["git", "describe", "--tags", "--match", "v*", "--always", "--dirty"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return "dev"
    return described or "dev"
