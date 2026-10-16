"""The site's sign-in: a password from CANARY_PASSWORD, a cookie that lasts
SIGNED_IN_S, an access token for other apps, and a check that each change
comes from this site.

    GET  /web/login      the sign-in page; ``next`` is where it goes after
    POST /web/login      the password: the cookie, then ``next``
    POST /web/logout     the cookie gone, then the sign-in page

With no password set, every route is open. With one, every route needs the
cookie except the ones the boards use and the files a page loads (is_open);
the routes in DATA also take the access token. After TRIES wrong
passwords in a row, an address waits WAIT_S.

Each POST, PUT, PATCH or DELETE whose Origin is another site gets 403, with a
password or without: a page on another site could otherwise post to this
one from a visitor's browser.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import quote

from flask import Blueprint, Flask, Response, g, jsonify, make_response, redirect, request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.middleware.proxy_fix import ProxyFix

from html_doc import Html
from web import ASSETS, page_head

log = logging.getLogger("login")

PASSWORD_ENV = "CANARY_PASSWORD"
SIGNED_IN_S = 30 * 86400
TRIES = 5
WAIT_S = 15 * 60
# A browser lets no HTTP page set a cookie over a Secure one of the same
# name, so an HTTPS sign-in has a cookie of its own.
COOKIE = "canary-sign-in"
SECURE_COOKIE = "__Secure-canary-sign-in"
HOME = "/web/"

# What the boards ask for, and what the sign-in page needs.
OPEN_GET = frozenset({"/", "/about", "/board-settings", "/calibration", "/firmware.bin",
                      "/firmware.merged.bin", "/install-firmware.sh", "/web/login"})
OPEN_POST = frozenset({"/sensor-readings", "/calibration", "/pair", "/web/login", "/web/logout"})
# epd's own files: the static folder, and the install page's scripts.
OPEN_PREFIXES = ("/static/", "/install/")
# The routes the access token reads.
DATA = frozenset({"/history", "/logs", "/status", "/sensor-readings", "/network.bin"})
CHANGES = frozenset({"POST", "PUT", "PATCH", "DELETE"})
FORWARDED = ("X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto")

WRONG = "Wrong password. Try again."
TOO_MANY = f"Too many tries. Try again in {WAIT_S // 60} minutes."
SIGNED_OUT = "Signed out. Reload the page to sign in again."
NEEDS_TOKEN = ("Not signed in. Send the access token from Settings, as "
               "Authorization: Bearer <token>.")
OTHER_SITE = "The request came from another site."
UNTRUSTED_PROXY = ("The request came through a reverse proxy. In config.yaml, set "
                   "server.reverse_proxy to true, then restart the server.")


def is_open(method: str, path: str) -> bool:
    """Whether a request needs no sign-in: a board's, or a file a page loads."""
    if method in ("GET", "HEAD"):
        if path in OPEN_GET or path.startswith(OPEN_PREFIXES):
            return True
        if path.count("/") == 1 and path.endswith(".png"):
            return True
        return path.startswith("/web/") and os.path.splitext(path)[1] in ASSETS
    return method == "POST" and path in OPEN_POST


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class Tries:
    """Wrong passwords by address. TRIES in a row, each within WAIT_S of the
    one before, make the address wait WAIT_S from the last; a right one
    forgets the address."""

    def __init__(self, now: Callable[[], float] = time.time):
        self.now = now
        self._by: dict[str, tuple[int, float]] = {}   # wrong in a row, and when the last came
        self._lock = threading.Lock()

    def wait(self, address: str) -> float:
        """The seconds ``address`` must still wait to try again; 0 for none."""
        with self._lock:
            count, last = self._by.get(address, (0, 0.0))
            left = last + WAIT_S - self.now()
            return left if count >= TRIES and left > 0 else 0.0

    def wrong(self, address: str) -> None:
        now = self.now()
        with self._lock:
            for old in [a for a, (_, last) in self._by.items() if now - last >= WAIT_S]:
                del self._by[old]
            count, _ = self._by.get(address, (0, 0.0))
            self._by[address] = (count + 1, now)

    def right(self, address: str) -> None:
        with self._lock:
            self._by.pop(address, None)


class Login:
    """Who may use the site: the password, the cookies signed with it, the
    access token and the wrong tries.

    ``path`` keeps the cookies' secret and the access token. It is written
    only once a password is set, so a server without one keeps no file.
    """

    def __init__(self, password: str, path: str, now: Callable[[], float] = time.time):
        self.password = password
        self.path = path
        self.tries = Tries(now)
        self._lock = threading.Lock()
        self._kept: dict[str, str] = self._read() if password else {}
        if password and not {"secret", "token"} <= self._kept.keys():
            self._kept.setdefault("secret", secrets.token_hex(32))
            self._kept.setdefault("token", secrets.token_urlsafe(32))
            self._write()

    @property
    def on(self) -> bool:
        return bool(self.password)

    def _read(self) -> dict[str, str]:
        try:
            with open(self.path) as f:
                kept = json.load(f)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            log.error("%s is unreadable (%s): every browser signs in again, and the "
                      "access token is new", self.path, exc)
            return {}
        return kept if isinstance(kept, dict) else {}

    def _write(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        part = self.path + ".part"
        fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(self._kept, f)
        os.replace(part, self.path)

    def _signer(self) -> URLSafeTimedSerializer:
        # The password is part of the key, so a new one ends every sign-in.
        key = hmac.new(bytes.fromhex(self._kept["secret"]), self.password.encode(),
                       hashlib.sha256).digest()
        return URLSafeTimedSerializer(key, salt="sign-in")

    def right(self, given: str) -> bool:
        return hmac.compare_digest(_digest(given), _digest(self.password))

    def cookie(self) -> str:
        return self._signer().dumps("in")

    def signed_in(self, *cookies: str | None) -> bool:
        """Whether one of ``cookies`` is a sign-in this server made, not older
        than SIGNED_IN_S."""
        for value in filter(None, cookies):
            try:
                if self._signer().loads(value, max_age=SIGNED_IN_S) == "in":
                    return True
            except BadSignature:
                pass
        return False

    @property
    def token(self) -> str:
        """The access token; empty with no password, when nothing needs one."""
        return self._kept.get("token", "")

    def replace_token(self) -> str:
        with self._lock:
            self._kept["token"] = secrets.token_urlsafe(32)
            self._write()
        return self.token

    def token_ok(self, given: str) -> bool:
        return bool(self.token and given) and hmac.compare_digest(_digest(given),
                                                                  _digest(self.token))


def _cookies() -> tuple[str | None, str | None]:
    return request.cookies.get(SECURE_COOKIE), request.cookies.get(COOKIE)


def _bearer() -> str:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def _problem(words: str, status: int) -> Response:
    rsp = jsonify(problem=words)
    rsp.status_code = status
    return rsp


def _local(path: str) -> str:
    """``path`` when it is a page of this site to go to after a sign-in;
    the browse page when it is not."""
    if not path.startswith("/") or path.startswith("//") or "\\" in path \
            or any(c.isspace() or not c.isprintable() for c in path) \
            or path.startswith("/web/login"):
        return HOME
    return path


def _sign_in_first() -> Response:
    if request.method == "GET" and "text/html" in request.headers.get("Accept", "") \
            and request.path not in DATA:
        there = request.full_path.rstrip("?")
        return redirect("/web/login?next=" + quote(there, safe="/"), 303)
    if request.method in CHANGES and "text/html" in request.headers.get("Accept", ""):
        return redirect("/web/login?next=" + quote(request.path, safe="/"), 303)
    if request.path not in DATA:
        return _problem(SIGNED_OUT, 401)
    rsp = _problem(NEEDS_TOKEN, 401)
    rsp.headers["WWW-Authenticate"] = 'Bearer realm="canary"'
    return rsp


def guard(app: Flask, login: Login, reverse_proxy: bool = False) -> None:
    """Put ``login`` in front of every route of ``app``, and the Origin check
    on every change. With ``reverse_proxy`` the visitor's address, scheme
    and host come from the proxy's X-Forwarded-* headers; without it the
    server ignores them, so nobody can fake an address."""
    if reverse_proxy:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    def same_site_only():
        if request.method not in CHANGES:
            return None
        origin = request.headers.get("Origin")
        if origin is None or origin.lower() == request.host_url.rstrip("/").lower():
            return None
        through_proxy = not reverse_proxy and any(h in request.headers for h in FORWARDED)
        return _problem(UNTRUSTED_PROXY if through_proxy else OTHER_SITE, 403)

    def signed_in_only():
        g.signed_in = login.on and login.signed_in(*_cookies())
        if not login.on or g.signed_in or is_open(request.method, request.path):
            return None
        if request.method in ("GET", "HEAD") and request.path in DATA \
                and login.token_ok(_bearer()):
            return None
        return _sign_in_first()

    app.before_request(same_site_only)
    app.before_request(signed_in_only)
    app.register_blueprint(login_blueprint(login))


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


def _page(html: str, status: int = 200) -> Response:
    rsp = make_response(html, status)
    rsp.headers["Cache-Control"] = "no-store"
    return rsp


def login_blueprint(login: Login) -> Blueprint:
    bp = Blueprint("login", __name__, url_prefix="/web")

    @bp.route("/login", methods=["GET"])
    def show():
        there = _local(request.args.get("next", HOME))
        if not login.on or login.signed_in(*_cookies()):
            return redirect(there, 303)
        return _page(login_html(there))

    @bp.route("/login", methods=["POST"])
    def sign_in():
        there = _local(request.form.get("next", HOME))
        if not login.on:
            return redirect(there, 303)
        address = request.remote_addr or ""
        if not login.tries.wait(address):
            if login.right(request.form.get("password", "")):
                login.tries.right(address)
                rsp = redirect(there, 303)
                secure = request.is_secure
                rsp.set_cookie(SECURE_COOKIE if secure else COOKIE, login.cookie(),
                               max_age=SIGNED_IN_S, path="/", secure=secure, httponly=True,
                               samesite="Lax")
                return rsp
            login.tries.wrong(address)
        wait = login.tries.wait(address)
        if not wait:
            return _page(login_html(there, WRONG), 401)
        rsp = _page(login_html(there, TOO_MANY), 429)
        rsp.headers["Retry-After"] = str(math.ceil(wait))
        return rsp

    @bp.route("/logout", methods=["POST"])
    def sign_out():
        rsp = redirect("/web/login", 303)
        rsp.delete_cookie(COOKIE, path="/")
        rsp.delete_cookie(SECURE_COOKIE, path="/", secure=True)
        return rsp

    return bp


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
