import pytest
from bs4 import BeautifulSoup
from epd_server.config import ConfigError
from flask import Flask

import epd_server.login as epd_login

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
    assert rsp.json == {"problem": epd_login.SIGNED_OUT}


def test_network_bin_needs_a_sign_in(client):
    assert client.get("/network.bin?product=canary-dock").status_code == 401
    sign_in(client)
    assert client.get("/network.bin?product=canary-dock").data == b"ok"


def test_the_terminal_install_signs_in_with_the_password_alone(client):
    rsp = client.post("/web/login", data={"password": PASSWORD})
    assert rsp.status_code == 303
    assert client.get("/network.bin?product=canary-dock").data == b"ok"


def test_with_no_password_every_route_is_open(tmp_path):
    login = Login("", str(tmp_path / "login.json"))
    client = site(login).test_client()
    for method, path in PEOPLE_ROUTES:
        assert client.open(path, method=method, headers=HTML).status_code == 200, path
    assert client.get("/web/login?next=/web/logs").headers["Location"] == "/web/logs"
    assert not (tmp_path / "login.json").exists()
    assert login.token == "" and not login.token_ok("")


# ── canary's page and settings ──────────────────────────────────────

def test_the_sign_in_page_is_in_the_sites_layout(client):
    rsp = sign_in(client, "wrong")
    page = BeautifulSoup(rsp.data, "html.parser")
    assert page.find(id="problem").text == epd_login.WRONG
    assert page.select_one(".brand").text == "Canary"
    assert page.find("input", {"name": "next"})["value"] == "/web/"


@pytest.mark.parametrize("path", sorted(lg.DATA))
def test_the_access_token_reads_the_data(client, login, path):
    rsp = client.get(path, headers={"Authorization": f"Bearer {login.token}"})
    assert rsp.data == b"ok"


def test_the_server_trusts_a_proxy_only_when_the_config_says_so():
    zone = {"timezone": "Europe/Dublin"}
    assert load_settings({"server": zone}).reverse_proxy is False
    assert load_settings({"server": {**zone, "reverse_proxy": True}}).reverse_proxy is True
    with pytest.raises(ConfigError, match="^server.reverse_proxy must be true or false$"):
        load_settings({"server": {**zone, "reverse_proxy": "yes"}})
