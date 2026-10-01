"""The splash screen: the logo, alone.

The display holds it in its firmware, and writes its own lines under the
logo: its version when it starts, other than from deep sleep, and a progress
bar and the version it installs while it writes an update. The bar fills by
partial updates, which the panel does only in black and white, so this page
is rendered in two levels with no dither.

``scripts/notices.py`` renders it into ``include/display/`` with the notices.
The server also serves it, for the hours the page schedule turns off
(``off_hours``).
"""
from __future__ import annotations

import os

from airium import Airium
from epd_server import GreyscaleQuantiser
from markupsafe import Markup

from .base import EnvPage

# Traced from the drawn logo by hardware/logo/trace.py. It sits here, not in
# hardware/, because the server's image holds only this folder.
LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "canary-logo-screen.svg")


def logo_svg() -> str:
    """The logo's SVG text, for SplashPage."""
    with open(LOGO) as f:
        return f.read()


class SplashPage(EnvPage):
    """The logo, centred on the panel."""
    requires = ()
    css_class = "splash"
    title = "CANARY"

    def __init__(self, logo_svg: str, **kwargs):
        kwargs.setdefault("quantiser", GreyscaleQuantiser(levels=2, dither=False))
        super().__init__("splash", **kwargs)
        self.logo_svg = logo_svg

    def body(self, a: Airium, **data) -> None:
        a.div(klass="logo", _t=Markup(self.logo_svg))
