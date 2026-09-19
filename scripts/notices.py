"""Render the head's notices into include/head/notices/.

Run from the repository root with the server's environment, which has the
renderer and its browser:

    server/.venv/bin/python scripts/notices.py

Only needed when a notice's wording or design changes; the PNGs are
committed, so the firmware build needs no browser.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))

from pages.notice import notices  # noqa: E402

OUT = os.path.join(ROOT, "include", "head", "notices")


def main() -> None:
    for page in notices(width=1280, height=720, png_dir=OUT):
        page.template()
        page.save()
        print(f"{page.png_path}: {os.path.getsize(page.png_path)} bytes")


if __name__ == "__main__":
    main()
