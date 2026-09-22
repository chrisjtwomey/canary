"""The pages in a browser, and the explorer's window onto the readings."""
from datetime import datetime

import pytest
from bs4 import BeautifulSoup
from epd_server import DisplayServer, ReadingsStore

from server import make_between, make_history, make_pages, make_source
from sources.mock import MockReadingsSource
from sources.status import DeviceReports
from tests.conftest import AT, TZ
from tests.html import attr, one
from web import MAX_POINTS, MAX_SPAN_S, MEASURES, WINDOWS, HistoryQuery, time_axis, web_blueprint

DAY = 86400


@pytest.fixture
def pages(tz):
    return make_pages(tz, width=1280, height=720)


@pytest.fixture
def history():
    return HistoryQuery(make_history(make_between(7, lambda: AT)), TZ, now=lambda: AT)


@pytest.fixture
def client(pages, source, history, tz):
    server = DisplayServer(pages=pages, source=source, schedule=[("00:00:00", "breathe.png")],
                           tz=tz, queries={"history": history.answer})
    server.app.register_blueprint(web_blueprint(pages, source))
    return server.app.test_client()


def soup_of(rsp):
    assert rsp.status_code == 200, rsp.status_code
    return BeautifulSoup(rsp.get_data(as_text=True), "html.parser")


class TestBrowse:
    def test_the_menu_links_every_page_under_a_heading(self, client, pages):
        soup = soup_of(client.get("/web/"))
        linked = [attr(a, "data-page") for a in soup.select("nav a[data-page]")]
        assert sorted(linked) == sorted(p.name for p in pages)
        assert [h.get_text() for h in soup.select("nav .heading")] == \
            ["Now", "Three days", "Changes", "Boards"]
        assert attr(one(soup, ".bar a.explore-link"), "href") == "explore"

    def test_the_stage_starts_on_the_first_page_at_the_panel_size(self, client, pages):
        frame = one(soup_of(client.get("/web/")), "#stage iframe")
        assert (attr(frame, "src"), attr(frame, "width"), attr(frame, "height")) == \
            (pages[0].name, "1280", "720")

    def test_web_without_the_slash_leads_to_the_browse_page(self, client):
        rsp = client.get("/web")
        assert rsp.status_code in (301, 308) and rsp.headers["Location"].endswith("/web/")


class TestLivePage:
    def test_a_page_is_built_from_the_readings_now(self, client, source):
        soup = soup_of(client.get("/web/breathe"))
        latest = source.datasets()["latest"]()
        assert one(soup, "div.page.page-breathe") is not None
        assert one(soup, "#co2 .value").get_text() == f"{latest['co2_ppm']:,.0f}"
        assert one(soup, "script#charts").get_text().startswith("[")

    def test_the_regenerated_page_keeps_its_own_document(self, client, pages):
        breathe = next(p for p in pages if p.name == "breathe")
        before = str(breathe.airium)
        client.get("/web/breathe")
        assert str(breathe.airium) == before

    @pytest.mark.parametrize("path", ["/web/styles.css", "/web/charts.js", "/web/web.css",
                                      "/web/fonts/Fraunces.ttf"])
    def test_the_assets_a_page_loads_are_served(self, client, path):
        assert client.get(path).status_code == 200

    @pytest.mark.parametrize("path", ["/web/breathe.html", "/web/../server.py", "/web/nope",
                                      "/web/config.yaml"])
    def test_nothing_else_in_the_directory_is(self, client, path):
        assert client.get(path).status_code == 404

    def test_a_name_with_no_page_says_so_and_keeps_the_menu(self, client, pages):
        rsp = client.get("/web/nope")
        assert rsp.status_code == 404
        soup = BeautifulSoup(rsp.get_data(as_text=True), "html.parser")
        assert one(soup, "#missing").get_text() == \
            "No page by that name. Pick one from the menu above."
        linked = [attr(a, "data-page") for a in soup.select("nav a[data-page]")]
        assert sorted(linked) == sorted(p.name for p in pages)


class TestExplore:
    def test_a_button_for_each_measurement_and_window(self, client):
        soup = soup_of(client.get("/web/explore"))
        assert [attr(b, "data-metric") for b in soup.select("#measures button")] == list(MEASURES)
        assert [attr(b, "data-hours") for b in soup.select("#windows button")] == \
            [str(h) for h, _ in WINDOWS]
        assert [attr(s, "src") for s in soup.find_all("script", src=True)] == \
            ["rough.iife.min.js", "charts.js", "explore.js"]
        assert one(soup, "#chart canvas#trace") and one(soup, "#chart canvas#overlay")


class TestHistory:
    def test_the_last_day_by_default(self, client):
        answer = client.get("/history?metric=co2").get_json()
        spec = answer["spec"]
        assert (answer["from"], answer["to"]) == (AT - DAY, AT)
        assert spec["x"] == {"min": AT - DAY, "max": AT}
        assert all(AT - DAY <= ts <= AT for ts, _ in spec["points"])
        assert spec["now"] == spec["points"][-1]
        assert answer["tz"] == "Europe/Dublin" and answer["unit"] == "ppm"

    def test_a_window_in_the_past_has_no_now_marker(self, history):
        spec = history.answer({"metric": "co2", "from": str(AT - 3 * DAY),
                               "to": str(AT - 2 * DAY)})["spec"]
        assert spec["now"] is None and spec["points"][-1][0] <= AT - 2 * DAY

    def test_span_counts_back_from_to(self, history):
        answer = history.answer({"metric": "dust", "span": str(6 * 3600), "to": str(AT - DAY)})
        assert (answer["from"], answer["to"]) == (AT - DAY - 6 * 3600, AT - DAY)

    def test_a_long_window_is_thinned_and_capped(self, history):
        answer = history.answer({"metric": "co2", "from": "0"})
        assert answer["to"] - answer["from"] == MAX_SPAN_S
        assert len(answer["spec"]["points"]) <= MAX_POINTS + 2

    def test_a_short_window_grows_to_an_hour(self, history):
        answer = history.answer({"metric": "co2", "span": "60"})
        assert answer["to"] - answer["from"] == 3600

    def test_temperature_carries_humidity_on_its_own_scale(self, history):
        answer = history.answer({"metric": "temperature"})
        assert answer["spec"]["points2"] and "y2" in answer["spec"]
        assert answer["second"] == {"title": "Humidity", "unit": "%"}
        assert answer["decimals"] == 1

    def test_the_words_name_the_high_and_the_low(self, history):
        detail = history.answer({"metric": "co2"})["detail"]
        assert detail.startswith("High of ") and ", low of " in detail

    def test_a_window_before_any_reading_says_so(self, tz):
        empty = HistoryQuery(lambda start, end: [], tz, now=lambda: AT)
        answer = empty.answer({"metric": "co2"})
        assert answer["spec"]["points"] == [] and answer["spec"]["now"] is None
        assert answer["detail"] == "No readings in this window. Try a longer one."

    @pytest.mark.parametrize("query", ["metric=radon", f"to={AT}&from={AT}", "from=yesterday",
                                       "span=a+while"])
    def test_a_bad_question_is_a_400(self, client, query):
        assert client.get("/history?" + query).status_code == 400


class TestTimeAxis:
    def test_a_day_is_labelled_by_the_hour(self):
        start = int(datetime(2026, 9, 3, 6, 0, tzinfo=TZ).timestamp())
        rules, labels = time_axis(start, start + DAY, TZ)
        assert [lb["label"] for lb in labels][:3] == ["06:00", "08:00", "10:00"]
        assert len(rules) == 1

    def test_three_days_by_the_day_and_a_week_by_its_short_name(self):
        _, three = time_axis(AT - 3 * DAY, AT, TZ)
        _, week = time_axis(AT - 7 * DAY, AT, TZ)
        assert [lb["label"] for lb in three] == ["Tuesday", "Wednesday", "Thursday"]
        assert week[0]["label"] == "Fri" and len(week) == 7

    def test_a_month_by_the_date_at_most_ten_times(self):
        rules, labels = time_axis(AT - 30 * DAY, AT, TZ)
        assert 1 < len(labels) <= 10 and len(rules) == len(labels)
        assert labels[0]["label"].split()[1] == "Aug"


def test_history_reads_the_store_with_pressure_at_sea_level(tmp_path):
    store = ReadingsStore(tmp_path / "sensor-readings.db")
    store.add_many([{"ts": AT - 60, "device": "canary-dock", "pressure_hpa": 1000.0},
                    {"ts": AT, "device": "canary-dock", "pressure_hpa": 1001.0}])
    docs = make_history(make_between(7, lambda: AT, store=store), altitude_m=80)(AT - 30, AT)
    assert docs == [{"ts": AT, "device": "canary-dock", "pressure_hpa": 1010.5,
                     "pressure_station_hpa": 1001.0}]


def test_the_simulated_room_stops_at_now():
    docs = MockReadingsSource(now=lambda: AT).between(AT - 600, AT + DAY)
    assert docs[0]["ts"] >= AT - 600 and docs[-1]["ts"] <= AT and len(docs) == 11


def test_the_live_page_and_the_panel_share_one_source(pages, tz):
    reports = DeviceReports(now=lambda: float(AT))
    source = make_source(7, lambda: AT, reports)
    server = DisplayServer(pages=pages, source=source, schedule=[("00:00:00", "breathe.png")], tz=tz)
    server.app.register_blueprint(web_blueprint(pages, source))
    soup = soup_of(server.app.test_client().get("/web/diagnostics"))
    assert one(soup, ".verdict").get_text() == "No report from either board yet."
