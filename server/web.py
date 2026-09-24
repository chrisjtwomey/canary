"""The pages in a browser, and one measurement over any stretch of time.

    GET /web/            every page, one at a time, scaled to the window
    GET /web/<page>      a page's HTML, built from the readings as they are now
    GET /web/stamp?page=<page>
                         what changes when the page would, and when the server
                         started; without a page, the readings'
    GET /web/explore     one measurement over a window the viewer moves
    GET /web/<asset>     the stylesheets, scripts and fonts those load
    GET /web/config      the server's config (config_page.py)
    GET /history?metric=co2&from=<epoch>&to=<epoch>
    GET /history?metric=co2&span=<seconds>
                         the explorer's chart, as a spec charts.js draws

A page is built at the panel's size, as the head gets it; the browse page
scales it to fit.
"""
from __future__ import annotations

import copy
import functools
import hashlib
import json
import math
import os
import time
from datetime import datetime, timedelta
from typing import Callable, Iterable

from airium import Airium
from epd_server.source import DataSource
from flask import Blueprint, jsonify, request, send_from_directory
from markupsafe import Markup

from html_doc import Html
from metrics import extremes, hour_ticks
from pages.base import HTML_DIR, EnvPage
from pages.diagnostics import DiagnosticsPage, DiagnosticsTracePage, HealthTracePage
from pages.pool import (CO2, IAQ, PM25, PRESSURE, RH, TEMP, DeltaPage, Metric, TracePage,
                        trace_points, value_range, value_ticks, weekday_axis)
from sources.readings import epoch_arg
from version import server_version

# The explorer's measurements, by the name its URL gives them.
MEASURES: dict[str, Metric] = {"co2": CO2, "temperature": TEMP, "humidity": RH, "dust": PM25,
                               "air": IAQ, "barometer": PRESSURE}
# The windows the explorer offers, in hours.
WINDOWS = ((6, "6 h"), (24, "24 h"), (72, "3 days"), (168, "7 days"), (720, "30 days"))
MIN_SPAN_S = 3600
MAX_SPAN_S = 92 * 86400
# A chart holds at most this many points; a longer window thins its readings.
MAX_POINTS = 720
# What /web/<asset> serves from the pages' directory. The directory also holds
# the HTML the renderer last wrote, which is stale by the time anyone asks.
ASSETS = (".css", ".js", ".ttf")


def label(page: EnvPage) -> str:
    """The page's name in the browse page's menu."""
    if isinstance(page, DiagnosticsPage):
        return "Boards"
    if isinstance(page, DiagnosticsTracePage):
        return "Board history"
    return page.title or page.name


# The two groups that list the same measurements: one row, with a switch.
SPANS = (("trace", "Three days"), ("delta", "Changes"))


def menu(pages: Iterable[EnvPage]) -> list[tuple[str, list[EnvPage]]]:
    """The pages under the headings the menu shows, each group in the server's order."""
    groups: dict[str, list[EnvPage]] = {"Now": [], "Three days": [], "Changes": [], "Boards": []}
    for page in pages:
        if isinstance(page, TracePage):
            groups["Three days"].append(page)
        elif isinstance(page, DeltaPage):
            groups["Changes"].append(page)
        elif isinstance(page, (DiagnosticsPage, DiagnosticsTracePage, HealthTracePage)):
            groups["Boards"].append(page)
        else:
            groups["Now"].append(page)
    return [(heading, group) for heading, group in groups.items() if group]


# A page as a phone shows it: upright, and narrow enough that the charts'
# fixed-size labels are still readable once scaled to a phone's width. The
# stylesheets lay a page out afresh when its box is taller than wide.
PORTRAIT = (540, 960)


def render_live(page: EnvPage, source: DataSource, portrait: bool = False) -> str:
    """``page``'s HTML from the readings now, at the panel's size or PORTRAIT.

    The template is built on a copy: the regeneration thread uses the page
    object itself, and a template replaces the page's document as it starts.
    """
    fetch = source.datasets()
    view = copy.copy(page)
    if portrait:
        view.image_width = view.image_inner_width = PORTRAIT[0]
        view.image_height = view.image_inner_height = PORTRAIT[1]
    view.live = True
    view.template(**{name: fetch[name]() for name in page.requires})
    return str(view.airium)


def data_stamp(requires: Iterable[str], source: DataSource) -> str:
    """A word that changes whenever a page built on ``requires`` would: the
    newest reading's time for a page of readings; for a page of the boards
    alone, their reports, refusals and which are offline."""
    requires = tuple(requires)
    fetch = source.datasets()
    if "latest" in requires:
        latest = fetch["latest"]()
        return str(latest.get("ts")) if latest else ""
    if any(name.startswith("status") for name in requires):
        status = fetch["status"]()
        if status is None:
            return ""
        boards = [(device, bool(b.get("offline")), (b.get("refused") or {}).get("count", 0))
                  for device, b in sorted(status["boards"].items())]
        text = json.dumps([status["count"], boards])
        return hashlib.sha1(text.encode()).hexdigest()[:8]
    return ""


def page_head(a: Airium, title: str, refresh: str = "") -> None:
    """The head every /web/ page has; ``refresh`` is a meta refresh's content."""
    with a.head():
        a.meta(charset="utf-8")
        a.meta(name="viewport", content="width=device-width, initial-scale=1")
        if refresh:
            a.meta(**{"http-equiv": "refresh", "content": refresh})
        a.title(_t=title)
        a.link(rel="stylesheet", href="styles.css")
        a.link(rel="stylesheet", href="web.css")


def _page_links(a: Airium, group: list[EnvPage], browse_href: str, current: str) -> None:
    for page in group:
        extra = {"aria-current": "page"} if page.name == current else {}
        a.a(href=f"{browse_href}#{page.name}", _t=label(page),
            **{"data-page": page.name}, **extra)


def _span_row(a: Airium, groups: dict[str, list[EnvPage]], browse_href: str,
              current: str) -> None:
    """The row whose heading switches between the two spans. A radio holds the
    choice, so the switch works with no JavaScript."""
    chosen = next((key for key, heading in SPANS
                   if any(p.name == current for p in groups[heading])), SPANS[0][0])
    with a.div(klass="group spans"):
        for key, _ in SPANS:
            a.input(type="radio", name="span", id=f"span-{key}",
                    **({"checked": "checked"} if key == chosen else {}))
        with a.div(klass="switcher"):
            for key, heading in SPANS:
                a.label(klass="heading", for_=f"span-{key}", _t=heading)
        for key, heading in SPANS:
            with a.div(klass="links", id=f"links-{key}"):
                _page_links(a, groups[heading], browse_href, current)


# The version cannot change while the process runs, and a checkout asks git
# for it.
own_version = functools.cache(server_version)


def menu_bar(a: Airium, pages: list[EnvPage], browse_href: str, current: str) -> None:
    """The menu across the top, with this server's version beside the name.
    ``browse_href`` is how a page link reaches the browse page from here;
    ``current`` names the page or view that is showing."""
    showing = next((p for p in pages if p.name == current), None)
    with a.header(klass="bar"):
        a.input(type="checkbox", id="menu-open", klass="menu-open")
        with a.div(klass="top"):
            with a.div(klass="name-line"):
                a.a(klass="brand label", href=browse_href or "./", _t="Canary")
                a.span(klass="version", id="server-version", title="Server version",
                       _t=own_version())
            with a.div(klass="views"):
                for view, words in (("explore", "Explore"), ("logs", "Logs"), ("config", "Config")):
                    extra = {"aria-current": "page"} if current == view else {}
                    a.a(klass=f"{view}-link", href=view, _t=words, **extra)
        with a.div(klass="here"):
            if showing is not None:
                a.button(type="button", klass="step", id="prev", _t="‹",
                         **{"aria-label": "Previous page"})
                a.span(klass="name", id="here-name", _t=label(showing))
                a.button(type="button", klass="step", id="next", _t="›",
                         **{"aria-label": "Next page"})
            a.label(klass="pages-toggle", for_="menu-open", _t="Pages")
        with a.nav():
            groups = dict(menu(pages))
            switched = all(heading in groups for _, heading in SPANS)
            for heading, group in menu(pages):
                if switched and heading == SPANS[1][1]:
                    continue
                if switched and heading == SPANS[0][1]:
                    _span_row(a, groups, browse_href, current)
                    continue
                with a.div(klass="group"):
                    a.span(klass="heading", _t=heading)
                    with a.div(klass="links"):
                        _page_links(a, group, browse_href, current)


def not_found_html(pages: list[EnvPage]) -> str:
    """The page a /web/ name with no page behind it gets."""
    a = Html()
    a("<!DOCTYPE html>")
    with a.html(lang="en"):
        page_head(a, "Canary \u00b7 Page not found")
        with a.body(klass="web config"):
            menu_bar(a, pages, "./", "")
            with a.main(klass="settings"):
                a.h1(klass="title label", _t="Page not found")
                a.p(klass="banner", id="missing",
                    _t="No page by that name. Pick one from the menu above.")
    return str(a)


def browse_html(pages: list[EnvPage]) -> str:
    """Every page, one at a time. browse.js picks the page from the URL's
    fragment, scales it to the window and reloads it every minute."""
    first = pages[0]
    a = Html()
    a("<!DOCTYPE html>")
    with a.html(lang="en"):
        page_head(a, "Canary")
        with a.body(klass="web browse"):
            menu_bar(a, pages, "", first.name)
            with a.main(klass="stage", id="stage"):
                a.iframe(id="page", src=first.name, title=label(first),
                         width=str(first.image_width), height=str(first.image_height))
            a.script(src="browse.js")
    return str(a)


def explore_html(pages: list[EnvPage]) -> str:
    """One measurement over a window. explore.js asks /history for each
    window the viewer picks and draws it with charts.js."""
    a = Html()
    a("<!DOCTYPE html>")
    with a.html(lang="en"):
        page_head(a, "Canary · Explore")
        with a.body(klass="web explore"):
            menu_bar(a, pages, "./", "explore")
            with a.main(klass="explorer"):
                with a.div(klass="controls"):
                    with a.div(klass="choice", id="measures", role="group",
                               **{"aria-label": "Measurement"}):
                        for stem, m in MEASURES.items():
                            a.button(type="button", _t=m.title, **{"data-metric": stem})
                    with a.div(klass="choice", id="windows", role="group",
                               **{"aria-label": "Window"}):
                        for hours, words in WINDOWS:
                            a.button(type="button", _t=words, **{"data-hours": str(hours)})
                    with a.div(klass="choice", id="steps", role="group",
                               **{"aria-label": "Move"}):
                        a.button(type="button", id="earlier", _t="‹ Earlier")
                        a.button(type="button", id="later", _t="Later ›")
                        a.button(type="button", id="latest", _t="Now")
                with a.div(klass="readout"):
                    with a.div(klass="top"):
                        a.div(klass="title label", id="title")
                        a.div(klass="stamp", id="stamp")
                    with a.div(klass="stats"):
                        with a.div(klass="hero", id="hero"):
                            a.span(klass="value", _t="—")
                            a.span(klass="unit")
                        a.div(klass="verdict", id="when")
                        a.div(klass="detail", id="detail")
                    with a.div(klass="chart", id="chart"):
                        a.canvas(id="trace")
                        a.canvas(id="overlay")
                a.p(klass="hint", _t="Drag the chart to move through time. "
                                     "Scroll or pinch on it to zoom.")
            a.script(src="rough.iife.min.js")
            a.script(src="charts.js")
            a.script(src="explore.js")
    return str(a)


# The level filter's choices: a level keeps the lines at it and above.
LEVEL_CHOICES = (("", "All levels"), ("DEBUG", "Debug and above"), ("INFO", "Info and above"),
                 ("NOTICE", "Notice and above"), ("WARNING", "Warnings and above"),
                 ("ERROR", "Errors and above"), ("CRITICAL", "Critical only"))


def logs_html(pages: list[EnvPage], logging_on: bool) -> str:
    """What the boards log, newest at the end. logs.js asks /logs for the
    lines and adds new ones as they arrive."""
    a = Html()
    a("<!DOCTYPE html>")
    with a.html(lang="en"):
        page_head(a, "Canary \u00b7 Logs")
        with a.body(klass="web logs"):
            menu_bar(a, pages, "./", "logs")
            with a.main(klass="logview"):
                if not logging_on:
                    a.p(klass="banner", id="logging-off",
                        _t=Markup('Board logging is off. Turn it on in <a href="config#mqtt">Config</a>.'))
                with a.div(klass="filters"):
                    with a.select(id="board", **{"aria-label": "Board"}):
                        a.option(value="", _t="All boards")
                    with a.select(id="level", **{"aria-label": "Level"}):
                        for value, words in LEVEL_CHOICES:
                            a.option(value=value, _t=words)
                    a.input(type="search", id="find", placeholder="Find text",
                            autocomplete="off", spellcheck="false", **{"aria-label": "Find text"})
                with a.div(klass="log", id="log", tabindex="0", **{"aria-label": "Board log"}):
                    a.button(type="button", id="earlier", klass="earlier", hidden="hidden",
                             _t="Show earlier lines")
                    a.ol(id="lines", _t="")
                    a.p(klass="empty", id="empty", hidden="hidden", _t="")
                a.p(klass="status", id="status", _t="", **{"aria-live": "polite"})
                a.button(type="button", id="newest", klass="newest", hidden="hidden",
                         _t="New lines below")
            a.script(src="logs.js")
    return str(a)


def web_blueprint(pages: list[EnvPage], source: DataSource, logging_on: bool = True) -> Blueprint:
    """The /web routes for ``pages``, each built from ``source`` when asked
    for. ``logging_on`` says whether boards' MQTT logs reach this server."""
    bp = Blueprint("web", __name__, url_prefix="/web")
    by_name = {p.name: p for p in pages}
    started = int(time.time())

    @bp.route("/")
    def browse():
        return browse_html(pages)

    @bp.route("/explore")
    def explore():
        return explore_html(pages)

    @bp.route("/logs")
    def logs():
        return logs_html(pages, logging_on)

    @bp.route("/stamp")
    def stamp():
        page = by_name.get(request.args.get("page", ""))
        requires = page.requires if page is not None else ("latest",)
        return jsonify(stamp=data_stamp(requires, source), started=started)

    @bp.route("/<path:name>")
    def page_or_asset(name: str):
        page = by_name.get(name)
        if page is not None:
            return render_live(page, source, portrait=request.args.get("shape") == "portrait")
        if os.path.splitext(name)[1] in ASSETS:
            return send_from_directory(HTML_DIR, name)
        return not_found_html(pages), 404

    return bp


def _clock(ts: int, tz) -> str:
    t = datetime.fromtimestamp(ts, tz)
    return f"{t:%a} {t.day} {t:%b}, {t:%H:%M}"


def time_axis(start: int, end: int, tz) -> tuple[list[dict], list[dict]]:
    """Rules and labels for the window's x axis: the hour inside two days,
    the day's name inside ten, and the date beyond."""
    hours = (end - start) / 3600
    if hours <= 48:
        every = next(e for e in (1, 2, 3, 6, 12) if hours / e <= 12)
        rules, _ = weekday_axis(start, end, tz)
        return rules, [{"x": t["x"], "label": f"{t['label']}:00"}
                       for t in hour_ticks(start, end, tz, every)]
    if hours <= 240:
        return weekday_axis(start, end, tz, "%A" if hours <= 96 else "%a")
    every = math.ceil(hours / 24 / 10)
    day = datetime.fromtimestamp(start, tz).replace(hour=0, minute=0, second=0, microsecond=0)
    rules, labels = [], []
    while day.timestamp() <= end:
        ts = int(day.timestamp())
        if ts > start and day.toordinal() % every == 0:
            rules.append({"x": ts})
            labels.append({"x": ts, "label": f"{day.day} {day:%b}"})
        day += timedelta(days=1)
    return rules, labels


class HistoryQuery:
    """The /history query: one measurement between two times, as a trace spec.

    Args:
        between: the readings from one epoch to another, oldest first.
        tz: the zone the axis and the words are in.
    """

    def __init__(self, between: Callable[[int, int], list[dict]], tz,
                 now: Callable[[], float] = time.time):
        self.between = between
        self.tz = tz
        self.now = now

    def answer(self, args: dict) -> dict:
        """The chart and its words for ``args``: ``metric``, one of MEASURES;
        ``to`` in epoch seconds, now by default; and where the window starts,
        as ``from`` in epoch seconds or ``span`` in seconds before ``to``,
        a day before it by default.

        A window shorter than an hour grows to one, and one longer than
        MAX_SPAN_S shrinks to it, each keeping its end.

        Raises:
            ValueError: an unknown metric, a time that is not a number, or
                a window that ends before it starts.
        """
        stem = args.get("metric") or "co2"
        m = MEASURES.get(stem)
        if m is None:
            raise ValueError(f"metric must be one of {', '.join(MEASURES)}")
        now = int(self.now())
        end = epoch_arg(args, "to", now)
        start = epoch_arg(args, "from", end - epoch_arg(args, "span", 86400))
        if end <= start:
            raise ValueError("the window must end after it starts")
        start = end - min(max(end - start, MIN_SPAN_S), MAX_SPAN_S)

        docs = self.between(start, end)
        step = max(60, (end - start) // MAX_POINTS)
        newest = docs[-1] if docs else None
        pts = trace_points(docs, m.key, start, newest, step)
        y = value_range(pts, m)
        rules, labels = time_axis(start, end, self.tz)
        spec = {
            "kind": "trace", "canvas": "#trace",
            "points": pts,
            "x": {"min": start, "max": end}, "y": y, "yticks": value_ticks(y),
            "guides": [{"y": v, "label": words} for v, words in m.guides],
            "days": rules, "dayLabels": labels,
            "now": pts[-1] if pts and end >= now - 600 else None,
        }
        if m.second is not None:
            pts2 = trace_points(docs, m.second.key, start, newest, step)
            spec["points2"] = pts2
            spec["y2"] = value_range(pts2, m.second)
            spec["label2"] = f"{m.second.title.lower()}, {m.second.unit}"

        lo, hi = extremes(docs, m.key)
        detail = (f"High of {m.fmt(hi[m.key])} on {_clock(hi['ts'], self.tz)}, "
                  f"low of {m.fmt(lo[m.key])} on {_clock(lo['ts'], self.tz)}."
                  if lo and hi else "No readings in this window. Try a longer one.")
        return {
            "metric": stem, "title": m.title, "unit": m.unit, "decimals": m.decimals,
            "from": start, "to": end, "now": now, "tz": getattr(self.tz, "key", "UTC"),
            "stamp": f"{_clock(start, self.tz)} – {_clock(end, self.tz)}",
            "detail": detail, "spec": spec,
            "second": None if m.second is None else {"title": m.second.title,
                                                      "unit": m.second.unit},
        }

