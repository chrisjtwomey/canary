"""Base page for this project.

``epd_server.page.Page`` renders. This subclass fixes what every page here
shares: the output locations, the eight-grey quantiser for the Inkplate 5
panel, the HTML scaffold, and the hand-off of chart specs to ``charts.js``.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo

from airium import Airium
from epd_server import GreyscaleQuantiser
from epd_server.page import Page as _Page

_SERVER_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
HTML_DIR = os.path.join(_SERVER_DIR, "static")
PNG_DIR = _SERVER_DIR

GREY_LEVELS = 8


class EnvPage(_Page):
    """A page of this project.

    Subclasses set ``title``, ``stylesheet`` and ``requires``, build the
    page in ``body()``, and return chart specs from ``charts()``.
    """

    title = ""
    stylesheet = ""
    css_class = ""   # the page-<css_class> hook the stylesheet keys on; defaults to the name
    live = False     # loads ago.js, for a browser; the panel's render has no clock to follow

    def __init__(self, name: str, tz: tzinfo | None = None, **kwargs):
        kwargs.setdefault("html_dir", HTML_DIR)
        kwargs.setdefault("png_dir", PNG_DIR)
        kwargs.setdefault("quantiser", GreyscaleQuantiser(levels=GREY_LEVELS))
        super().__init__(name, **kwargs)
        self.tz = tz or ZoneInfo("UTC")

    def body(self, a: Airium, **data) -> None:
        raise NotImplementedError

    def charts(self, **data) -> list[dict]:
        return []

    def local(self, ts: int) -> datetime:
        return datetime.fromtimestamp(ts, self.tz)

    def waiting(self, a: Airium) -> None:
        """The page before the board has posted a reading."""
        a.div(klass="title label", _t=self.title or self.name)
        a.div(klass="verdict", _t="No readings yet.")
        a.div(klass="detail", _t="The board posts once it connects.")

    def template(self, **data):
        waiting = "latest" in self.requires and data.get("latest") is None
        self.airium = Airium()
        a = self.airium
        a("<!DOCTYPE html>")
        with a.html(lang="en"):
            with a.head():
                a.meta(charset="utf-8")
                a.meta(name="viewport", content="width=device-width, initial-scale=1")
                a.title(_t=self.title or self.name)
                a.link(rel="stylesheet", href="styles.css")
                if self.stylesheet:
                    a.link(rel="stylesheet", href=self.stylesheet)
                a.script(src="rough.iife.min.js")
                a.script(src="charts.js")
                if self.live:
                    a.script(src="ago.js")
            with a.body(style=self.layout_css_variables()):
                with a.div(klass="inner-canvas-outer"):
                    with a.div(klass="inner-canvas"):
                        hook = "waiting" if waiting else self.css_class or self.name
                        with a.div(klass=f"inner-canvas-content page page-{hook}"):
                            if waiting:
                                self.waiting(a)
                            else:
                                self.body(a, **data)
                specs = json.dumps([] if waiting else self.charts(**data)).replace("<", "\\u003c")
                a.script(type="application/json", id="charts", _t=specs)
                a.script(_t="Charts.render(JSON.parse(document.getElementById('charts').textContent));")
