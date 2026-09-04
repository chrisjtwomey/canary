"""Each page builds the DOM it promises and hands charts.js the specs it draws."""
import json
import re

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

    def test_today_line_counts_stuffy_minutes_and_airings(self, data, tz):
        soup, _ = render(BreathePage("breathe", tz=tz, width=WIDTH, height=HEIGHT), data)
        line = text(soup, "#today")
        assert line.startswith("Above 1,000 ppm for ")
        assert re.search(r" today\. Aired at (08:59|09:0\d)\.$", line), line

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


from metrics import (barometer_word, classify_rate, iaq_verdict, pm25_verdict, pressure_meaning,  # noqa: E402
                     rate_words, value_at)
from pages.air import AirPage  # noqa: E402
from pages.pool import PRESSURE, TEMP, DeltaPage, TracePage  # noqa: E402
from pages.diagnostics import DiagnosticsPage  # noqa: E402
from pages.dust import MAX_DOTS, DustPage  # noqa: E402


class TestDust:
    def test_hero_verdict_and_cloud(self, data, tz):
        latest = data["latest"]
        soup, specs = render(DustPage("dust", tz=tz, width=WIDTH, height=HEIGHT), data)
        assert text(soup, "#pm25 .value") == fmt_int(latest["pm2_5"])
        assert text(soup, ".verdict") == pm25_verdict(latest["pm2_5"])
        assert text(soup, ".detail").startswith(f"PM1 {latest['pm1_0']} · PM10 {latest['pm10']}.")
        (cloud,) = specs
        assert cloud["kind"] == "dotcloud" and cloud["canvas"] == "#dust-cloud"
        total = sum(d["n"] for d in cloud["dots"])
        assert 0 < total <= MAX_DOTS
        assert [d["rough"] for d in cloud["dots"]] == [False] * 5 + [True]

    def test_fan_warming_up(self, data, tz):
        latest = {k: v for k, v in data["latest"].items() if not k.startswith(("pm", "pc_"))}
        latest["valid"] = dict(data["latest"]["valid"], particulates=False)
        soup, specs = render(DustPage("dust", tz=tz, width=WIDTH, height=HEIGHT), dict(data, latest=latest))
        assert text(soup, "#pm25 .value") == "—"
        assert text(soup, "#pm25 .cold-tag") == "fan warming up"
        assert text(soup, ".verdict") == "Warming up."
        assert specs[0]["dots"] == []


class TestAir:
    def test_index_hero_scale_and_spark(self, data, tz):
        latest = data["latest"]
        soup, specs = render(AirPage("air", tz=tz, width=WIDTH, height=HEIGHT), data)
        assert text(soup, "#iaq .value") == f"{latest['iaq']:.0f}"
        assert text(soup, ".verdict") == iaq_verdict(latest["iaq"])
        assert "accuracy high, 3 of 3" in text(soup, ".detail")
        spark, scale = specs
        assert spark["kind"] == "sparkline" and spark["points"][-1] == [latest["ts"], latest["iaq"]]
        assert scale["kind"] == "scale" and scale["value"] == latest["iaq"]
        assert [z["label"] for z in scale["zones"]] == [
            "excellent", "good", "light", "moderate", "heavy", "severe", "extreme"]

    def test_without_an_index_the_gas_resistance_is_the_hero(self, data, tz):
        latest = {k: v for k, v in data["latest"].items() if k not in ("iaq", "iaq_accuracy")}
        soup, specs = render(AirPage("air", tz=tz, width=WIDTH, height=HEIGHT), dict(data, latest=latest))
        assert text(soup, "#iaq .value") == f"{latest['gas_ohm'] / 1000:.0f}"
        assert text(soup, "#iaq .unit") == "kΩ"
        assert text(soup, ".verdict") == "No index yet."
        assert "BSEC" in text(soup, ".detail")
        assert specs[1]["value"] is None

    def test_heater_cold(self, data, tz):
        latest = {k: v for k, v in data["latest"].items() if k not in ("iaq", "iaq_accuracy", "gas_ohm")}
        latest["valid"] = dict(data["latest"]["valid"], gas=False)
        soup, _ = render(AirPage("air", tz=tz, width=WIDTH, height=HEIGHT), dict(data, latest=latest))
        assert text(soup, "#iaq .value") == "—"
        assert text(soup, "#iaq .cold-tag") == "heater warming up"


class TestBarometerPool:
    def test_trace_shows_three_days_with_the_legends_as_guides(self, data72, tz):
        latest = data72["latest"]
        soup, specs = render(TracePage("barometer-trace", PRESSURE, tz=tz, width=WIDTH, height=HEIGHT), data72)
        assert text(soup, ".title") == "Barometer"
        assert text(soup, "#now .value") == f"{latest['pressure_hpa']:.1f}"
        assert text(soup, ".verdict") == barometer_word(latest["pressure_hpa"]) + "."
        assert text(soup, ".detail").startswith("High of ")
        (trace,) = specs
        assert trace["kind"] == "trace" and trace["x"] == {"min": latest["ts"] - 3 * 86400, "max": latest["ts"]}
        assert [g["label"] for g in trace["guides"]] == ["rain", "change", "fair", "very dry"]
        assert [d["label"] for d in trace["dayLabels"]] == ["Tuesday", "Wednesday", "Thursday"]
        assert trace["points"][-1] == [latest["ts"], latest["pressure_hpa"]]
        assert trace["recent"][-1] == trace["points"][-1]
        assert 250 <= len(trace["points"]) <= 300

    def test_delta_is_the_hour_change_with_its_meaning(self, data, tz):
        latest, history = data["latest"], data["history_24h"]
        soup, specs = render(DeltaPage("barometer-delta", PRESSURE, tz=tz, width=WIDTH, height=HEIGHT), data)
        delta = latest["pressure_hpa"] - value_at(history, "pressure_hpa", latest["ts"] - 3600)
        assert text(soup, "#delta-pressure_hpa .value") == f"{delta:+.1f}"
        assert text(soup, "#delta-pressure_hpa .unit") == "hPa in 1 h"
        rate = classify_rate(delta, 0.6, 1.2)
        assert text(soup, "#rate-pressure_hpa") == rate_words(rate)
        assert text(soup, "#meaning-pressure_hpa") == pressure_meaning(rate, latest["pressure_hpa"])
        (col,) = specs
        assert col["kind"] == "column" and col["value"] == latest["pressure_hpa"]
        assert col["max"] - col["min"] == 30
        assert [mk["label"] for mk in col["marks"]] == ["1 h ago", "3 h ago"]

    def test_comfort_delta_carries_humidity_as_a_second_block(self, data, tz):
        soup, specs = render(DeltaPage("comfort-delta", TEMP, tz=tz, width=WIDTH, height=HEIGHT), data)
        assert text(soup, "#delta-temp_c .unit") == "°C in 15 min"
        assert text(soup, "#delta-rh_pct .unit") == "% in 15 min"
        assert [c["canvas"] for c in specs] == ["#column", "#column2"]

    def test_cold_sensor_on_both_shapes(self, data72, tz):
        latest = {k: v for k, v in data72["latest"].items() if k != "pressure_hpa"}
        latest["valid"] = dict(data72["latest"]["valid"], pressure=False)
        soup, _ = render(TracePage("barometer-trace", PRESSURE, tz=tz, width=WIDTH, height=HEIGHT),
                         dict(data72, latest=latest))
        assert text(soup, "#now .cold-tag") == "no reading" and text(soup, ".verdict") == "Warming up."
        soup, specs = render(DeltaPage("barometer-delta", PRESSURE, tz=tz, width=WIDTH, height=HEIGHT),
                             {"latest": latest, "history_24h": data72["history_72h"]})
        assert text(soup, "#delta-pressure_hpa .value") == "—" and specs[0]["value"] is None


STATUS = {
    "doc": {
        "ts": 1788511219, "device": "inkplate5-env-monitor",
        "valid": {"temp_humidity": True, "co2": True, "particulates": False, "pressure": True, "gas": True},
        "client": {
            "board": "Inkplate5V2", "version": "v0.1.0-dev", "ip": "192.168.1.35", "rssi": -61,
            "uptime_s": 8040, "heap_free": 120000, "heap_size": 327680,
            "psram_free": 4000000, "psram_size": 4194304, "panel_temp_c": 27,
            "width": 1280, "height": 720, "rotation": 0, "mock_sensors": True,
            "sensors": {"shtc3": True, "scd41": True, "pmsa003i": True, "bme688": False},
            "fetch": {"next_url": "http://h:8080/day.png", "next_in_s": 120, "backoff_step": 0,
                      "ok": 12, "failed": 1},
        },
    },
    "age_s": 40,
    "count": 3,
}


class TestDiagnostics:
    def test_every_card_reads_the_report(self, tz):
        soup, specs = render(DiagnosticsPage("diagnostics", tz=tz, width=WIDTH, height=HEIGHT),
                             {"status": STATUS})
        assert text(soup, ".title") == "Inkplate5V2"
        assert text(soup, ".stamp") == "reported 40 s ago, report 3"
        assert text(soup, "#version") == "v0.1.0-dev"
        assert text(soup, "#uptime") == "2 h 14 min"
        assert text(soup, "#mock") == "mocks"
        assert text(soup, "#ip") == "192.168.1.35"
        assert text(soup, "#rssi") == "-61 dBm, good"
        assert text(soup, "#heap") == "117 KB free of 320 KB"
        assert text(soup, "#panel-temp") == "27 °C"
        assert text(soup, "#sensor-shtc3") == "ok"
        assert text(soup, "#sensor-pmsa003i") == "warming up"
        assert text(soup, "#sensor-bme688") == "missing"
        assert text(soup, "#next-page") == "day.png"
        assert text(soup, "#fetches") == "12 ok, 1 failed"
        bars, heap, psram = specs
        assert bars == {"kind": "bars", "canvas": "#rssi-bars", "filled": 3, "total": 4}
        assert heap["fraction"] == pytest.approx((327680 - 120000) / 327680)
        assert psram["canvas"] == "#psram-meter"

    def test_no_report_yet(self, tz):
        page = DiagnosticsPage("diagnostics", tz=tz, width=WIDTH, height=HEIGHT)
        assert page.requires == ("status",)
        soup, specs = render(page, {"status": None})
        assert text(soup, ".empty .verdict") == "No report from the board yet."
        assert specs == []
