"""Corrections applied to the readings before the pages see them."""
from epd_server.source import StaticSource

from server import make_history
from sources.corrections import CorrectedSource, without_uncalibrated_iaq


def test_pressure_is_corrected_and_the_station_value_kept():
    inner = StaticSource(latest={"ts": 1, "pressure_hpa": 1000.0},
                         history_24h=[{"ts": 0, "pressure_hpa": 1000.0}, {"ts": 1}])
    ds = CorrectedSource(inner, altitude_m=80).datasets()
    latest = ds["latest"]()
    assert latest["pressure_hpa"] == 1009.5 and latest["pressure_station_hpa"] == 1000.0
    history = ds["history_24h"]()
    assert history[0]["pressure_hpa"] == 1009.5 and "pressure_hpa" not in history[1]


def test_zero_altitude_leaves_the_pressure_as_measured():
    inner = StaticSource(latest={"ts": 1, "pressure_hpa": 1000.0})
    assert CorrectedSource(inner, 0).datasets()["latest"]() == {"ts": 1, "pressure_hpa": 1000.0}


def test_an_index_below_high_accuracy_is_held_back_and_its_accuracy_kept():
    for accuracy in (0, 1, 2):
        doc = {"ts": 1, "iaq": 200, "iaq_accuracy": accuracy, "gas_ohm": 720000}
        assert without_uncalibrated_iaq(doc) == {"ts": 1, "iaq_accuracy": accuracy, "gas_ohm": 720000}


def test_an_index_at_high_accuracy_is_kept():
    doc = {"ts": 1, "iaq": 85, "iaq_accuracy": 3}
    assert without_uncalibrated_iaq(doc) is doc


def test_an_index_without_its_accuracy_is_held_back():
    assert without_uncalibrated_iaq({"ts": 1, "iaq": 85}) == {"ts": 1}


def test_the_source_and_the_history_hold_back_the_same_readings():
    docs = [{"ts": 0, "iaq": 60, "iaq_accuracy": 3}, {"ts": 1, "iaq": 190, "iaq_accuracy": 1}]
    inner = StaticSource(latest=docs[1], history_24h=docs)
    ds = CorrectedSource(inner, 0).datasets()
    assert "iaq" not in ds["latest"]()
    assert [d.get("iaq") for d in ds["history_24h"]()] == [60, None]
    history = make_history(lambda start, end: docs)
    assert [d.get("iaq") for d in history(0, 1)] == [60, None]
