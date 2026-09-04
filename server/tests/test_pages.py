"""Each page builds the DOM it promises and hands charts.js the specs it draws."""
import json

import pytest
from bs4 import BeautifulSoup

from metrics import co2_verdict, comfort_verdict, fmt_int
from pages.breathe import BreathePage
from pages.comfort import ComfortPage
from pages.day import DayPage
from server import make_pages

WIDTH, HEIGHT = 1280, 720


def render(page, data):
    page.template(**data)
    soup = BeautifulSoup(str(page.airium), "html.parser")
    specs = json.loads(soup.find("script", id="charts").string)
    return soup, specs


def text(soup, selector):
    node = soup.select_one(selector)
    assert node is not None, selector
    return node.get_text(strip=True)


def cold(latest):
    """A cold boot: the CO2 sensor has not produced a reading yet."""
    doc = {k: v for k, v in latest.items() if k != "co2_ppm"}
    doc["valid"] = dict(latest["valid"], co2=False)
    return doc


def test_every_page_requires_only_datasets_the_source_provides(source, tz):
    names = set(source.datasets())
    for page in make_pages(tz, width=WIDTH, height=HEIGHT):
        assert set(page.requires) <= names, page.name


def test_page_css_hook_follows_the_class_not_the_instance_name(data, tz):
    soup, _ = render(BreathePage("breathe-preview", tz=tz, width=WIDTH, height=HEIGHT), data)
    assert soup.select_one("div.page.page-breathe") is not None
    assert soup.find("link", href="breathe.css") is not None


def test_scaffold_loads_rough_and_charts_and_sets_the_layout(data, tz):
    soup, _ = render(BreathePage("breathe", tz=tz, width=WIDTH, height=HEIGHT), data)
    assert [s["src"] for s in soup.find_all("script", src=True)] == ["rough.iife.min.js", "charts.js"]
    assert "--outer-width:1280px" in soup.body["style"]
    assert "Charts.render" in soup.find_all("script")[-1].string


class TestBreathe:
    def test_hero_verdict_and_sparkline(self, data, tz):
        latest = data["latest"]
        soup, specs = render(BreathePage("breathe", tz=tz, width=WIDTH, height=HEIGHT), data)
        assert text(soup, ".title") == "Carbon dioxide"
        assert text(soup, "#co2 .value") == fmt_int(latest["co2_ppm"])
        assert text(soup, ".verdict") == co2_verdict(latest["co2_ppm"])
        assert soup.select_one("#co2.cold") is None

        (spark,) = specs
        assert spark["kind"] == "sparkline" and spark["canvas"] == "#co2-spark"
        assert spark["x"] == {"min": latest["ts"] - 3 * 3600, "max": latest["ts"]}
        assert spark["points"][-1] == [latest["ts"], latest["co2_ppm"]]
        assert spark["now"] == [latest["ts"], latest["co2_ppm"]]
        assert spark["y"]["min"] == 400
        assert [t["label"] for t in spark["ticks"]] == ["19", "20", "21"]

    def test_detail_says_when_now_is_the_days_high(self, data, tz):
        soup, _ = render(BreathePage("breathe", tz=tz, width=WIDTH, height=HEIGHT), data)
        assert text(soup, ".detail").startswith("Now at the day's high. Low of ")

    def test_cold_sensor_keeps_the_layout_and_says_so(self, data, tz):
        cold_data = dict(data, latest=cold(data["latest"]))
        soup, specs = render(BreathePage("breathe", tz=tz, width=WIDTH, height=HEIGHT), cold_data)
        assert soup.select_one("#co2.cold") is not None
        assert text(soup, "#co2 .value") == "—"
        assert text(soup, "#co2 .cold-tag") == "warming up"
        assert text(soup, ".verdict") == "Warming up."
        (spark,) = specs
        assert spark["now"] is None
        (warm,) = render(BreathePage("breathe", tz=tz, width=WIDTH, height=HEIGHT), data)[1]
        assert len(spark["points"]) == len(warm["points"]) - 1


class TestComfort:
    def test_numbers_verdict_and_chart(self, data, tz):
        latest = data["latest"]
        soup, specs = render(ComfortPage("comfort", tz=tz, width=WIDTH, height=HEIGHT), data)
        assert text(soup, "#temp .value") == f"{latest['temp_c']:.1f}"
        assert text(soup, "#rh .value") == f"{latest['rh_pct']:.0f}"
        assert text(soup, ".verdict") == comfort_verdict(latest["temp_c"], latest["rh_pct"])
        assert text(soup, ".detail").startswith("Dew point ")

        (chart,) = specs
        assert chart["kind"] == "comfort" and chart["canvas"] == "#comfort-chart"
        assert [z["t"] for z in chart["zones"]] == [[17.0, 26.0], [19.0, 24.0]]
        assert chart["now"] == [latest["temp_c"], latest["rh_pct"]]
        assert 30 <= len(chart["trail"]) <= 40
        for t, rh in chart["trail"]:
            assert 10 < t < 35 and 0 <= rh <= 100

    def test_cold_sensor(self, data, tz):
        latest = {k: v for k, v in data["latest"].items() if k not in ("temp_c", "rh_pct")}
        latest["valid"] = dict(data["latest"]["valid"], temp_humidity=False)
        soup, specs = render(ComfortPage("comfort", tz=tz, width=WIDTH, height=HEIGHT), dict(data, latest=latest))
        assert text(soup, "#temp .cold-tag") == "warming up"
        assert text(soup, ".verdict") == "Warming up."
        assert specs[0]["now"] is None


class TestDay:
    def test_four_ribbons_and_an_axis(self, data, tz):
        latest = data["latest"]
        soup, specs = render(DayPage("day", tz=tz, width=WIDTH, height=HEIGHT), data)
        assert text(soup, ".head-now .label") == "Current"
        assert text(soup, ".head-hist .label") == "Last 24 hours"
        assert soup.select_one(".now #now-co2_ppm") is not None
        assert soup.select_one(".hist #range-co2_ppm") is not None
        assert soup.select_one(".hist #rib-co2_ppm") is not None
        assert text(soup, "#now-co2_ppm .value") == fmt_int(latest["co2_ppm"])
        assert text(soup, "#now-temp_c .value") == f"{latest['temp_c']:.1f}"
        assert [c["id"] for c in soup.find_all("canvas")] == [
            "rib-co2_ppm", "rib-pm2_5", "rib-temp_c", "rib-rh_pct", "rib-axis"]

        ribbons, axis = specs[:4], specs[4]
        window = {"min": latest["ts"] - 24 * 3600, "max": latest["ts"]}
        for rib in ribbons:
            assert rib["kind"] == "ribbon" and rib["x"] == window
            assert rib["points"][-1][0] == latest["ts"]
            assert all(window["min"] <= a < b <= window["max"] for a, b in rib["nights"])
            assert "extremes" not in rib
        assert axis["kind"] == "axis" and [t["label"] for t in axis["ticks"]] == ["00", "06", "12", "18"]

    def test_each_row_names_the_days_high_and_low(self, data, tz):
        latest, history = data["latest"], data["history_24h"]
        soup, _ = render(DayPage("day", tz=tz, width=WIDTH, height=HEIGHT), data)
        rng = soup.select_one("#range-co2_ppm")
        assert [t.get_text() for t in rng.select(".tag")] == ["high", "low"]
        values = [d["co2_ppm"] for d in history + [latest]]
        assert [v.get_text() for v in rng.select(".v")] == [fmt_int(max(values)), fmt_int(min(values))]
        for t in rng.select(".t"):
            assert len(t.get_text()) == 5 and t.get_text()[2] == ":"

    def test_ribbon_points_are_thinned_to_five_minutes(self, data, tz):
        _, specs = render(DayPage("day", tz=tz, width=WIDTH, height=HEIGHT), data)
        pts = specs[0]["points"]
        assert 280 <= len(pts) <= 292
        assert all(b[0] - a[0] >= 300 for a, b in zip(pts, pts[1:-1]))
