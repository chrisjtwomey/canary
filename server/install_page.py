"""/web/install: epd's install page in this site's layout, with the network
settings the boards get above the board list.

Each setting saves when a person leaves its field, through /web/config, which
checks it and keeps the old file as it does for every setting; these take
effect without a restart. epd's install.js draws the boards from the config
in the script element beside the form, which install-form.js renews after
each save from /web/install/config.
"""
from __future__ import annotations

import dataclasses
from typing import Callable

from epd_server.install import config_json
from flask import Blueprint, jsonify, make_response
from markupsafe import Markup

import config_form as cf
from config_page import View, _field, file_view
from html_doc import Html
from pages.base import EnvPage
from web import menu_bar, page_head


def network_fields(view: View) -> list[cf.Field]:
    """The install page's fields: the MQTT broker only while the boards log
    over MQTT, since the page has no MQTT switch to show it by."""
    mqtt_on = view.values.get("mqtt.enabled") == "true"
    return [dataclasses.replace(f, when="") for f in cf.INSTALL_FIELDS if not f.when or mqtt_on]


def install_html(pages: list[EnvPage], config: dict, view: View) -> str:
    a = Html()
    a("<!DOCTYPE html>")
    with a.html(lang="en"):
        page_head(a, "Canary · Install")
        with a.body(klass="web config"):
            menu_bar(a, pages, "./", "install")
            with a.main(klass="settings install", id="install"):
                a.h1(klass="title label", _t="Install firmware")
                with a.form(method="post", action="config", id="network-form",
                            novalidate="novalidate"):
                    a.input(type="hidden", name="mode", value="form")
                    with a.section(klass="panel sheet"):
                        with a.div(klass="fields"):
                            for f in network_fields(view):
                                _field(a, f, view, [], "", sheet=True)
                    a.p(klass="note", id="network-status", _t="", **{"aria-live": "polite"})
            a.script(type="application/json", id="install-config", _t=Markup(config_json(config)))
            a.script(src="rough.iife.min.js")
            a.script(src="install-form.js")
            a.script(type="module", src="../install/install.js")
            a.script(type="module", src="install-sketch.js")
    return str(a)


def install_blueprint(pages: list[EnvPage], path: str, install: Callable[[], dict]) -> Blueprint:
    """The install page for the config file at ``path``. ``install`` gives
    epd's config for the page's script."""
    bp = Blueprint("install", __name__, url_prefix="/web")

    @bp.route("/install")
    def show():
        with open(path) as f:
            view = file_view(f.read())
        rsp = make_response(install_html(pages, install(), view))
        rsp.headers["Cache-Control"] = "no-store"
        return rsp

    @bp.route("/install/config")
    def values():
        rsp = jsonify(install())
        rsp.headers["Cache-Control"] = "no-store"
        return rsp

    return bp
