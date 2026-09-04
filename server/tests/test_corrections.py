"""Pressure reduced to sea level before the pages see it."""
from epd_server.source import StaticSource

from sources.corrections import SeaLevelSource


def test_pressure_is_corrected_and_the_station_value_kept():
    inner = StaticSource(latest={"ts": 1, "pressure_hpa": 1000.0},
                         history_24h=[{"ts": 0, "pressure_hpa": 1000.0}, {"ts": 1}])
    ds = SeaLevelSource(inner, altitude_m=80).datasets()
    latest = ds["latest"]()
    assert latest["pressure_hpa"] == 1009.5 and latest["pressure_station_hpa"] == 1000.0
    history = ds["history_24h"]()
    assert history[0]["pressure_hpa"] == 1009.5 and "pressure_hpa" not in history[1]


def test_zero_altitude_passes_the_source_through():
    inner = StaticSource(latest={"ts": 1, "pressure_hpa": 1000.0})
    assert SeaLevelSource(inner, 0).datasets()["latest"]() == {"ts": 1, "pressure_hpa": 1000.0}
