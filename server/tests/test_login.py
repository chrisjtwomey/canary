import json

import pytest
from bs4 import BeautifulSoup
from epd_server.config import ConfigError
from flask import Flask
from freezegun import freeze_time

import login as lg
from login import Login, guard, is_open
from server import load_settings

PASSWORD = "correct horse"
HTML = {"Accept": "text/html,application/xhtml+xml"}
JSON = {"Accept": "application/json"}


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


def site(login: Login, reverse_proxy: bool = False) -> Flask:
    """Every route answers "ok", behind ``login``."""
    app = Flask(__name__)

    @app.route("/", methods=["GET", "POST"])
    @app.route("/<path:name>", methods=["GET", "POST"])
    def anything(name=""):
        return "ok"

    guard(app, login, reverse_proxy)
    return app


@pytest.fixture
def login(tmp_path, clock):
    return Login(PASSWORD, str(tmp_path / "login.json"), now=clock)


@pytest.fixture
def client(login):
    return site(login).test_client()


def sign_in(client, password=PASSWORD, address="10.0.0.2", **kw):
    return client.post("/web/login", data={"password": password, "next": "/web/"},
                       environ_base={"REMOTE_ADDR": address}, **kw)


# ── Which routes need a sign-in ──────────────────────────────────────

BOARD_ROUTES = [("GET", "/"), ("GET", "/breathe.png"), ("GET", "/firmware.bin"),
                ("GET", "/firmware.merged.bin"), ("GET", "/install-firmware.sh"),
                ("GET", "/about"), ("GET", "/calibration"), ("GET", "/board-settings"),
                ("POST", "/sensor-readings"), ("POST", "/calibration"), ("POST", "/pair")]
PAGE_FILES = [("GET", "/web/web.css"), ("GET", "/web/config.js"),
              ("GET", "/web/fonts/x.ttf"), ("GET", "/static/install/install.js"),
              ("GET", "/install/install.js"), ("GET", "/web/login")]
PEOPLE_ROUTES = [("GET", "/web/"), ("GET", "/web/config"), ("POST", "/web/config"),
                 ("GET", "/web/install"), ("GET", "/web/breathe"), ("GET", "/web/logs"),
                 ("GET", "/network.bin"), ("GET", "/install"), ("GET", "/history"),
                 ("GET", "/logs"), ("GET", "/status"), ("GET", "/sensor-readings"),
                 ("GET", "/web/config/export/sensor-readings"), ("GET", "/web/sub/page.png"),
                 ("GET", "/anything-new"), ("POST", "/anything-new")]


@pytest.mark.parametrize("method, path", BOARD_ROUTES + PAGE_FILES)
def test_the_boards_routes_and_a_pages_files_need_no_sign_in(method, path):
    assert is_open(method, path)


@pytest.mark.parametrize("method, path", PEOPLE_ROUTES)
def test_every_other_route_needs_a_sign_in(method, path):
    assert not is_open(method, path)


@pytest.mark.parametrize("method, path", BOARD_ROUTES)
def test_a_board_reaches_its_routes_with_a_password_set(client, method, path):
    assert client.open(path, method=method).status_code == 200


def test_a_page_asks_a_browser_to_sign_in_and_comes_back_after(client):
    rsp = client.get("/web/config?tab=dock", headers=HTML)
    assert rsp.status_code == 303
    assert rsp.headers["Location"] == "/web/login?next=/web/config%3Ftab%3Ddock"
    form = BeautifulSoup(client.get(rsp.headers["Location"]).data, "html.parser")
    assert form.find("input", {"name": "next"})["value"] == "/web/config?tab=dock"
    rsp = client.post("/web/login", data={"password": PASSWORD, "next": "/web/config?tab=dock"})
    assert (rsp.status_code, rsp.headers["Location"]) == (303, "/web/config?tab=dock")
    assert client.get("/web/config", headers=HTML).data == b"ok"


def test_a_script_on_a_page_that_has_signed_out_is_told_to_reload(client):
    rsp = client.post("/web/config", headers=JSON)
    assert rsp.status_code == 401
    assert rsp.json == {"problem": lg.SIGNED_OUT}


def test_network_bin_needs_a_sign_in(client):
    assert client.get("/network.bin?product=canary-dock").status_code == 401
    sign_in(client)
    assert client.get("/network.bin?product=canary-dock").data == b"ok"


def test_with_no_password_every_route_is_open(tmp_path):
    login = Login("", str(tmp_path / "login.json"))
    client = site(login).test_client()
    for method, path in PEOPLE_ROUTES:
        assert client.open(path, method=method, headers=HTML).status_code == 200, path
    assert client.get("/web/login?next=/web/logs").headers["Location"] == "/web/logs"
    assert not (tmp_path / "login.json").exists()
    assert login.token == "" and not login.token_ok("")


# ── The sign-in ──────────────────────────────────────────────────────

def test_a_sign_in_over_http_sets_a_cookie_for_30_days_that_scripts_cannot_read(client):
    cookie = sign_in(client).headers["Set-Cookie"]
    assert cookie.startswith(lg.COOKIE + "=")
    assert "Max-Age=2592000" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie
    assert "Secure" not in cookie


def test_a_sign_in_over_https_sets_a_secure_cookie_of_its_own(login):
    client = site(login).test_client()
    cookie = client.post("/web/login", data={"password": PASSWORD},
                         base_url="https://canary.local").headers["Set-Cookie"]
    assert cookie.startswith(lg.SECURE_COOKIE + "=") and "Secure" in cookie
    assert client.get("/web/", base_url="https://canary.local").data == b"ok"


def test_a_wrong_password_says_so_and_sets_no_cookie(client):
    rsp = sign_in(client, "wrong")
    assert rsp.status_code == 401 and "Set-Cookie" not in rsp.headers
    page = BeautifulSoup(rsp.data, "html.parser")
    assert page.find(id="problem").text == lg.WRONG
    assert client.get("/web/", headers=HTML).status_code == 303


def test_a_sign_in_lasts_30_days(client):
    with freeze_time("2026-10-15 12:00:00") as frozen:
        sign_in(client)
        frozen.tick(30 * 86400 - 60)
        assert client.get("/web/").data == b"ok"
        frozen.tick(120)
        assert client.get("/web/").status_code == 401


def test_sign_out_ends_the_sign_in(client):
    sign_in(client)
    rsp = client.post("/web/logout")
    assert (rsp.status_code, rsp.headers["Location"]) == (303, "/web/login")
    assert client.get("/web/").status_code == 401


def restarted(client, password: str, path: str):
    """A client of a new server on ``path`` with ``password``, holding the cookie ``client`` holds."""
    again = site(Login(password, path)).test_client()
    again.set_cookie(lg.COOKIE, client.get_cookie(lg.COOKIE).value)
    return again


def test_a_new_password_ends_every_sign_in(client, login):
    sign_in(client)
    assert restarted(client, "another one", login.path).get("/web/").status_code == 401


def test_a_sign_in_survives_a_restart(client, login):
    sign_in(client)
    assert restarted(client, PASSWORD, login.path).get("/web/").data == b"ok"


def test_a_cookie_another_server_signed_is_refused(tmp_path, client):
    other = Login(PASSWORD, str(tmp_path / "other.json"))
    client.set_cookie(lg.COOKIE, other.cookie())
    assert client.get("/web/").status_code == 401


@pytest.mark.parametrize("asked", ["//evil.example/", "https://evil.example/", "/\\evil",
                                   "/\t/evil.example/", "/\n/evil.example/", "web/", "/web/login"])
def test_a_sign_in_goes_only_to_a_page_of_this_site(client, asked):
    rsp = client.post("/web/login", data={"password": PASSWORD, "next": asked})
    assert rsp.headers["Location"] == "/web/"


def test_the_keep_file_holds_no_password(login):
    kept = open(login.path).read()
    assert PASSWORD not in kept and set(json.loads(kept)) == {"secret", "token"}


# ── Wrong tries ──────────────────────────────────────────────────────

def test_five_wrong_tries_make_that_address_wait_15_minutes(client, clock):
    for _ in range(lg.TRIES - 1):
        assert sign_in(client, "wrong").status_code == 401
    rsp = sign_in(client, "wrong")
    assert rsp.status_code == 429 and rsp.headers["Retry-After"] == "900"
    assert BeautifulSoup(rsp.data, "html.parser").find(id="problem").text == lg.TOO_MANY
    assert sign_in(client).status_code == 429
    assert sign_in(client, address="10.0.0.3").status_code == 303
    clock.t += lg.WAIT_S
    assert sign_in(client).status_code == 303


def test_tries_while_waiting_do_not_make_the_wait_longer(client, clock):
    for _ in range(lg.TRIES):
        sign_in(client, "wrong")
    clock.t += lg.WAIT_S - 1
    assert sign_in(client, "wrong").status_code == 429
    clock.t += 1
    assert sign_in(client).status_code == 303


def test_a_right_password_forgets_the_wrong_ones(client):
    for _ in range(lg.TRIES - 1):
        sign_in(client, "wrong")
    sign_in(client)
    client.post("/web/logout")
    assert sign_in(client, "wrong").status_code == 401


def test_wrong_tries_far_apart_do_not_add_up(client, clock):
    for _ in range(lg.TRIES * 2):
        assert sign_in(client, "wrong").status_code == 401
        clock.t += lg.WAIT_S


# ── The token ────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", sorted(lg.DATA))
def test_the_access_token_reads_the_data(client, login, path):
    rsp = client.get(path, headers={"Authorization": f"Bearer {login.token}"})
    assert rsp.data == b"ok"


@pytest.mark.parametrize("method, path", [("GET", "/web/config"), ("GET", "/network.bin"),
                                          ("POST", "/web/config"), ("GET", "/web/")])
def test_the_access_token_opens_nothing_else(client, login, method, path):
    rsp = client.open(path, method=method, headers={"Authorization": f"Bearer {login.token}"})
    assert rsp.status_code == 401


def test_an_app_without_the_token_is_told_how_to_send_it(client):
    rsp = client.get("/status", headers={"Authorization": "Bearer wrong"})
    assert rsp.status_code == 401 and rsp.json == {"problem": lg.NEEDS_TOKEN}
    assert rsp.headers["WWW-Authenticate"] == 'Bearer realm="canary"'


def test_a_replaced_token_reads_nothing(client, login):
    old = login.token
    new = login.replace_token()
    assert new != old and login.token == new
    assert client.get("/status", headers={"Authorization": f"Bearer {old}"}).status_code == 401
    assert client.get("/status", headers={"Authorization": f"Bearer {new}"}).data == b"ok"


def test_the_access_token_is_made_once_and_kept_across_a_restart(login):
    assert len(login.token) >= 43
    again = Login(PASSWORD, login.path)
    assert again.token == login.token
    assert again.token_ok(login.token) and not again.token_ok(login.token + "x")


# ── Changes from another site ────────────────────────────────────────

@pytest.mark.parametrize("password", ["", PASSWORD])
def test_a_change_from_another_site_is_refused(tmp_path, password):
    client = site(Login(password, str(tmp_path / "login.json"))).test_client()
    if password:
        sign_in(client)
    for origin in ("http://evil.example", "null", "http://localhost:8443"):
        rsp = client.post("/web/config", headers={"Origin": origin})
        assert rsp.status_code == 403 and rsp.json == {"problem": lg.OTHER_SITE}, origin
    assert client.post("/web/config", headers={"Origin": "http://localhost"}).data == b"ok"
    assert client.post("/web/config").data == b"ok"


def test_a_board_post_from_another_site_is_refused(client):
    rsp = client.post("/sensor-readings", headers={"Origin": "http://evil.example"})
    assert rsp.status_code == 403


def test_a_page_from_another_site_can_still_be_read(client):
    sign_in(client)
    assert client.get("/web/", headers={"Origin": "http://evil.example"}).data == b"ok"


# ── Behind a reverse proxy ───────────────────────────────────────────

PROXIED = {"X-Forwarded-For": "203.0.113.9", "X-Forwarded-Host": "canary.example.com",
           "X-Forwarded-Proto": "https"}


def test_a_trusted_proxy_gives_the_visitors_address_host_and_scheme(login):
    client = site(login, reverse_proxy=True).test_client()
    for _ in range(lg.TRIES):
        sign_in(client, "wrong", headers=PROXIED)
    assert sign_in(client, headers=PROXIED).status_code == 429
    other = {**PROXIED, "X-Forwarded-For": "203.0.113.10"}
    rsp = sign_in(client, headers=other)
    assert rsp.status_code == 303 and "Secure" in rsp.headers["Set-Cookie"]
    rsp = client.post("/web/config", headers={**other, "Origin": "https://canary.example.com"})
    assert rsp.data == b"ok"


def test_without_the_setting_the_proxys_headers_change_nothing(client):
    for i in range(lg.TRIES):
        sign_in(client, "wrong", headers={"X-Forwarded-For": f"203.0.113.{i}"})
    assert sign_in(client).status_code == 429


def test_a_change_through_an_untrusted_proxy_says_how_to_trust_it(client):
    rsp = client.post("/web/config", headers={**PROXIED, "Origin": "https://canary.example.com"})
    assert rsp.status_code == 403 and rsp.json == {"problem": lg.UNTRUSTED_PROXY}


def test_the_server_trusts_a_proxy_only_when_the_config_says_so():
    zone = {"timezone": "Europe/Dublin"}
    assert load_settings({"server": zone}).reverse_proxy is False
    assert load_settings({"server": {**zone, "reverse_proxy": True}}).reverse_proxy is True
    with pytest.raises(ConfigError, match="^server.reverse_proxy must be true or false$"):
        load_settings({"server": {**zone, "reverse_proxy": "yes"}})
