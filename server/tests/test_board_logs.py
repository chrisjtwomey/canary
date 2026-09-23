"""GET /logs, the Logs view it serves, and the log store as a file."""
import json
from zoneinfo import ZoneInfo

import pytest
from bs4 import BeautifulSoup
from epd_server import LogStore
from flask import Flask

from board_logs import MAX_LINES, LogsQuery
from server import load_settings, make_pages
from tests.html import attr, one
from transfer import Overlap, Transfer
from web import web_blueprint

TZ = ZoneInfo("Europe/Dublin")


@pytest.fixture
def store(tmp_path):
    clock = [1_790_000_000.0]

    def now():
        clock[0] += 1
        return clock[0]

    s = LogStore(str(tmp_path / "board-logs.db"), now=now)
    for n in range(5):
        s.add("canary-dock", f"INFO - reading {n}")
    s.add("canary-head", "WARNING - fetch took 3 tries")
    s.add("canary-dock", "ERROR - POST failed")
    return s


@pytest.fixture
def pages(tz):
    return make_pages(tz, width=1280, height=720)


@pytest.fixture
def query(store):
    return LogsQuery(store, TZ)


def test_the_newest_lines_every_board_and_the_zone(query):
    answer = query.answer({"limit": "3"})
    assert [line["text"] for line in answer["lines"]] == \
        ["INFO - reading 4", "WARNING - fetch took 3 tries", "ERROR - POST failed"]
    assert answer["boards"] == ["canary-dock", "canary-head"]
    assert answer["tz"] == "Europe/Dublin"


def test_paging_forward_and_back(query):
    assert [line["id"] for line in query.answer({"after": "5"})["lines"]] == [6, 7]
    assert [line["id"] for line in query.answer({"before": "3"})["lines"]] == [1, 2]


def test_filters(query):
    assert [line["board"] for line in query.answer({"board": "canary-head"})["lines"]] == ["canary-head"]
    assert [line["level"] for line in query.answer({"level": "WARNING"})["lines"]] == ["WARNING", "ERROR"]
    assert [line["text"] for line in query.answer({"q": "POST"})["lines"]] == ["ERROR - POST failed"]
    assert query.answer({"board": "", "level": "", "q": ""})["lines"] == query.answer({})["lines"]


def test_an_answer_is_capped(query, monkeypatch):
    asked = {}
    monkeypatch.setattr(query.store, "lines", lambda **kw: asked.update(kw) or [])
    query.answer({"limit": "100000"})
    assert asked["limit"] == MAX_LINES


@pytest.mark.parametrize("args", [{"after": "x"}, {"limit": "1.5"}, {"level": "LOUD"}])
def test_a_bad_argument_is_refused(query, args):
    with pytest.raises(ValueError):
        query.answer(args)


def test_the_logs_view_has_its_filters_and_says_when_logging_is_off(query, pages, source):
    app = Flask(__name__)
    app.register_blueprint(web_blueprint(pages, source, logging_on=False))
    soup = BeautifulSoup(app.test_client().get("/web/logs").get_data(as_text=True), "html.parser")
    assert one(soup, "#logging-off").get_text() == "Board logging is off. Turn it on in Config."
    assert attr(one(soup, "#logging-off a"), "href") == "config#mqtt"
    assert [o.get_text() for o in soup.select("#board option")] == ["All boards"]
    assert [attr(o, "value") for o in soup.select("#level option")] == \
        ["", "DEBUG", "INFO", "NOTICE", "WARNING", "ERROR", "CRITICAL"]
    assert attr(one(soup, "#find"), "placeholder") == "Find text"
    assert one(soup, ".bar .views a[aria-current=page]").get_text() == "Logs"

    app = Flask(__name__)
    app.register_blueprint(web_blueprint(pages, source, logging_on=True))
    soup = BeautifulSoup(app.test_client().get("/web/logs").get_data(as_text=True), "html.parser")
    assert soup.select_one("#logging-off") is None


def test_the_log_store_goes_out_as_a_file_and_back_in_once(store, tmp_path):
    out = Transfer("board-logs", store.path, "logs")
    lines = list(out.lines())
    assert json.loads(lines[-1]) == {"board": "canary-dock", "received": pytest.approx(1_790_000_007.0),
                                     "level": 4, "text": "ERROR - POST failed"}
    elsewhere = LogStore(str(tmp_path / "other.db"))
    into = Transfer("board-logs", elsewhere.path, "logs")
    assert into.take(lines) == {"added": 7, "held": 0, "total": 7}
    with pytest.raises(Overlap):
        into.take(lines)
    assert into.take(lines, overwrite=True)["total"] == 7
    assert elsewhere.count() == 7, "a line put in again replaces itself"


def test_settings_keep_board_logs_a_week_under_the_canary_prefix():
    s = load_settings({})
    assert (s.logs_path, s.logs_days) == ("board-logs.db", 7)
    assert s.core.mqtt.prefix == "mqtt/canary"
    s = load_settings({"logs": {"keep_days": 2}, "mqtt": {"prefix": "home/canary"}})
    assert s.logs_days == 2 and s.core.mqtt.prefix == "home/canary"
