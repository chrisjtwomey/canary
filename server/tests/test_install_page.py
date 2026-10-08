"""The install page: epd's page in this site's layout, with the network
settings the boards get above the board list."""
import json

import pytest
from bs4 import BeautifulSoup
from flask import Flask

import config_form as cf
from install_page import install_blueprint
from server import make_pages
from tests.html import attr, one

CONFIG = {"boards": [], "missing": ["client.wifi.ssid"], "networkHere": True,
          "ssid": "</script><b>"}
FILE = ('client:\n  server_url: "http://canary.local:8080"\n  wifi:\n    ssid: Home\n'
        '    password: "pass word"\nmqtt:\n  enabled: {mqtt}\n  host: broker.lan\n')


@pytest.fixture
def page(tmp_path, tz):
    def get(mqtt=True):
        path = tmp_path / "config.yaml"
        path.write_text(FILE.format(mqtt=str(mqtt).lower()))
        app = Flask(__name__)
        app.register_blueprint(install_blueprint(make_pages(tz, width=1280, height=720),
                                                 str(path), lambda: dict(CONFIG)))
        rsp = app.test_client().get("/web/install")
        assert rsp.status_code == 200
        return rsp
    return get


def soup_of(rsp):
    return BeautifulSoup(rsp.get_data(as_text=True), "html.parser")


def test_the_page_carries_epds_config_and_scripts_in_the_sites_layout(page):
    rsp = page()

    soup = soup_of(rsp)
    assert rsp.headers["Cache-Control"] == "no-store"
    assert json.loads(one(soup, "script#install-config").string) == CONFIG
    assert [attr(s, "src") for s in soup.select("script[src]")] == [
        "rough.iife.min.js", "install-form.js", "../install/install.js", "install-sketch.js"]
    assert one(soup, "main#install h1").get_text() == "Install firmware"
    assert attr(one(soup, '.bar .views a[href="install"]'), "aria-current") == "page"


def test_the_page_renews_its_values_from_the_server_after_a_save(tmp_path, tz):
    path = tmp_path / "config.yaml"
    path.write_text(FILE.format(mqtt="true"))
    served = [dict(CONFIG), {**CONFIG, "missing": []}]
    app = Flask(__name__)
    app.register_blueprint(install_blueprint(make_pages(tz, width=1280, height=720),
                                             str(path), lambda: served.pop(0)))
    client = app.test_client()
    client.get("/web/install")

    rsp = client.get("/web/install/config")

    assert rsp.get_json() == {**CONFIG, "missing": []}
    assert rsp.headers["Cache-Control"] == "no-store"


def test_the_network_settings_sit_above_the_boards_and_save_as_each_field_is_left(page):
    form = one(soup_of(page()), "main#install form#network-form")

    assert attr(form, "action") == "config"
    assert [attr(f, "data-field") for f in form.select("[data-field]")] == \
        [f.key for f in cf.INSTALL_FIELDS]
    assert attr(one(form, "#f-client-wifi-ssid"), "value") == "Home"
    password = one(form, "#f-client-wifi-password")
    assert (attr(password, "type"), attr(password, "value")) == ("password", "pass word")
    assert one(form, ".reveal").get_text() == "Show"
    assert attr(one(form, "#f-client-mqtt_host"), "data-default") == "broker.lan"
    assert not form.select("button[type=submit], button[value]")
    assert attr(one(form, "#network-status"), "aria-live") == "polite"


def test_the_mqtt_broker_shows_only_while_the_boards_log_over_mqtt(page):
    form = one(soup_of(page(mqtt=False)), "form#network-form")

    assert "client.mqtt_host" not in [attr(f, "data-field") for f in form.select("[data-field]")]
    assert not form.select("[data-when]")
