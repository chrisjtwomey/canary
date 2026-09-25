"""The splash screen the head holds in its firmware: the logo, alone.

The head draws it when it starts, other than from deep sleep, and while it
writes an update, with the progress bar and a line of its own under the logo.
The bar fills by partial updates, which the panel does only in black and
white, so this page is rendered in two levels with no dither.

``scripts/notices.py`` renders it into ``include/head/`` with the notices.
"""
from __future__ import annotations

from airium import Airium
from epd_server import GreyscaleQuantiser
from markupsafe import Markup

from .base import EnvPage


class SplashPage(EnvPage):
    """The logo from ``hardware/canary-logo-screen.svg``, centred on the panel."""
    requires = ()
    css_class = "splash"
    title = "CANARY"

    def __init__(self, logo_svg: str, **kwargs):
        kwargs.setdefault("quantiser", GreyscaleQuantiser(levels=2, dither=False))
        super().__init__("splash", **kwargs)
        self.logo_svg = logo_svg

    def body(self, a: Airium, **data) -> None:
        a.div(klass="logo", _t=Markup(self.logo_svg))
