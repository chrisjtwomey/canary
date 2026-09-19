"""The notices the head draws itself, rendered here so they look like pages.

A notice replaces the page when the head cannot show one: the server is not
answering, or it and the display run versions that cannot work together,
with or without an image on the server that would bring them back together.
The head holds each as a PNG in its firmware, drawn by the same call that
draws a fetched page, and writes the facts it only knows at run time on the
lines the layout leaves free at the bottom.

``scripts/notices.py`` renders them into ``include/head/notices/``. They are
rendered again only when their wording or design changes, so the firmware
build needs no browser.
"""
from __future__ import annotations

from airium import Airium

from .base import EnvPage


class NoticePage(EnvPage):
    """A label, a verdict and a line of detail, with the bottom left free."""
    requires = ()
    css_class = "notice"

    def __init__(self, name: str, label: str, verdict: str, detail: str, **kwargs):
        super().__init__(name, **kwargs)
        self.title = label
        self.verdict = verdict
        self.detail = detail

    def body(self, a: Airium, **data) -> None:
        a.div(klass="title label", _t=self.title)
        a.div(klass="verdict", _t=self.verdict)
        a.div(klass="detail", _t=self.detail)


def notices(**kwargs) -> list[NoticePage]:
    return [
        NoticePage("notice-unreachable", "NO CONNECTION",
                   "Server unreachable.",
                   "Retrying. Pages resume when the server responds.", **kwargs),
        NoticePage("notice-version", "VERSION MISMATCH",
                   "Server version not supported.",
                   "Waiting for a firmware update from the server.", **kwargs),
        NoticePage("notice-no-firmware", "VERSION MISMATCH",
                   "No matching firmware on server.",
                   "Add firmware for the server's version, or update the server.", **kwargs),
    ]
