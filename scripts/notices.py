"""Render the head's notices into include/head/notices/, and its splash screen
into include/head/.

Run from the repository root with the server's environment, which has the
renderer and its browser:

    server/.venv/bin/python scripts/notices.py

Only needed when a notice's wording or design changes, or the logo's; the
PNGs are committed, so the firmware build needs no browser.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))

from pages.notice import notices  # noqa: E402
from pages.splash import SplashPage  # noqa: E402

OUT = os.path.join(ROOT, "include", "head", "notices")
SPLASH_OUT = os.path.join(ROOT, "include", "head")
LOGO = os.path.join(ROOT, "hardware", "canary-logo-screen.svg")


def main() -> None:
    with open(LOGO) as f:
        splash = SplashPage(f.read(), width=1280, height=720, png_dir=SPLASH_OUT)
    for page in [*notices(width=1280, height=720, png_dir=OUT), splash]:
        page.template()
        page.save()
        print(f"{page.png_path}: {os.path.getsize(page.png_path)} bytes")


if __name__ == "__main__":
    main()
