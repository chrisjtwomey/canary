"""canary's sign-in, on epd's: the password's variable, the routes the boards
and pages use, and the sign-in page in the site's layout.

With no password set, every route is open. See epd_server.login.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from epd_server.login import Login, SignInSite, board_route
from epd_server.login import guard as epd_guard
from flask import Flask

from html_doc import Html
from web import ASSETS, page_head

PASSWORD_ENV = "CANARY_PASSWORD"

# What the boards ask for beyond epd's routes.
OPEN_GET = frozenset({"/about", "/board-settings", "/calibration"})
OPEN_POST = frozenset({"/sensor-readings", "/calibration"})
# The routes the access token reads.
DATA = frozenset({"/history", "/logs", "/status", "/sensor-readings", "/network.bin"})


def is_open(method: str, path: str) -> bool:
    """Whether a request needs no sign-in: a board's, or a file a page loads."""
    if board_route(method, path):
        return True
    if method in ("GET", "HEAD"):
        return path in OPEN_GET or path == "/web/login" \
            or (path.startswith("/web/") and os.path.splitext(path)[1] in ASSETS)
    return method == "POST" and path in OPEN_POST | {"/web/login", "/web/logout"}


def login_html(next_path: str, problem: str = "") -> str:
    a = Html()
    a("<!DOCTYPE html>")
    with a.html(lang="en"):
        page_head(a, "Canary · Sign in")
        with a.body(klass="web config"):
            with a.header(klass="bar"):
                with a.div(klass="top"):
                    with a.div(klass="name-line"):
                        a.span(klass="brand label", _t="Canary")
            with a.main(klass="settings sign-in"):
                a.h1(klass="title label", _t="Sign in")
                if problem:
                    a.p(klass="banner problem", id="problem", _t=problem)
                with a.form(method="post", action="login", id="sign-in-form"):
                    a.input(type="hidden", name="next", value=next_path)
                    with a.div(klass="fields"):
                        with a.div(klass="field"):
                            with a.div(klass="head"):
                                a.label(klass="name", for_="password", _t="Password")
                            with a.div(klass="control"):
                                a.input(type="password", id="password", name="password",
                                        autocomplete="current-password", autofocus="autofocus",
                                        required="required")
                    with a.div(klass="choice"):
                        a.button(type="submit", klass="primary", _t="Sign in")
    return str(a)


SITE = SignInSite("canary", is_open=is_open, data=DATA, home="/web/", prefix="/web", page=login_html)


def guard(app: Flask, login: Login, reverse_proxy: bool = False) -> None:
    """Put ``login`` in front of every route of ``app``, as epd's guard does."""
    epd_guard(app, login, SITE, reverse_proxy)


@dataclass
class SignInState:
    """What the Settings page says of the sign-in. ``replaced`` says the
    access token was just replaced; ``boards`` are each board's name and keys."""
    on: bool
    token: str = ""
    replaced: bool = False
    boards: list = field(default_factory=list)


def state(login: Login) -> SignInState:
    return SignInState(on=login.on, token=login.token)
