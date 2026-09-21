"""The two places this repo names an epd version must agree.

``server/requirements.txt`` pins the server core. The CI workflow checks the
firmware's headers out at a ref. Both sides implement one contract — the
``EPD-Next-*`` headers — so a bump that moves only one of them builds the
firmware against a library the code has outgrown. That is what left the
workflow on v0.5.1 while the code needed 0.6.0.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "build.yaml"
REQUIREMENTS = ROOT / "server" / "requirements.txt"


def _workflow_epd_ref() -> str:
    """The ref every epd checkout in the workflow uses."""
    steps = [
        step
        for job in yaml.safe_load(WORKFLOW.read_text())["jobs"].values()
        for step in job.get("steps", [])
        if (step.get("with") or {}).get("repository") == "chrisjtwomey/epd"
    ]
    assert steps, f"no step in {WORKFLOW.name} checks epd out; rewrite this test"

    refs = {step["with"].get("ref") for step in steps}
    assert len(refs) == 1, f"epd is checked out at more than one ref: {sorted(refs)}"
    return refs.pop()


def _requirements_epd_pin() -> str:
    """The tag requirements.txt pins epd-server to."""
    pin = re.search(r"epd-server @ git\+\S+?@(\S+?)#", REQUIREMENTS.read_text())
    assert pin, "requirements.txt no longer pins epd-server to a tag"
    return pin.group(1)


def test_ci_builds_the_firmware_against_the_pinned_epd():
    assert _workflow_epd_ref() == _requirements_epd_pin()
