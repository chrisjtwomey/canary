"""The Python room matches the firmware room, and the source emits READINGS.md documents."""
import json

import pytest

from sources.mock import EnvModel, MockReadingsSource, reading_from, rh_from_abs

MIDNIGHT = 1756857600  # 2025-09-03 00:00 UTC


def at(hour):
    return MIDNIGHT + int(hour * 3600)


def test_deterministic_for_a_seed():
    a, b = EnvModel(3), EnvModel(3)
    a.reset(at(12)); b.reset(at(12))
    a.advance_to(at(20)); b.advance_to(at(20))
    assert (a.co2, a.temp, a.noise(1.0)) == (b.co2, b.temp, b.noise(1.0))


def test_xorshift_matches_the_c_sequence():
    # The firmware mock pins the same three draws (test_env_model:
    # test_xorshift_sequence_is_pinned), so both rooms run the same sequence.
    m = EnvModel(5)
    assert [m._rnd() for _ in range(3)] == [1351845, 336141829, 3472693697]
    m = EnvModel(5)
    assert [int(m.uniform() * 16777216) for _ in range(3)] == [5280, 1313054, 13565209]


def test_co2_rises_in_the_evening_and_decays_overnight():
    m = EnvModel(1)
    m.reset(at(17.5))
    before = m.co2
    m.advance_to(at(20))
    evening = m.co2
    assert evening > before + 100
    m.advance_to(at(30))
    assert 420 <= m.co2 < evening - 100


def test_cooking_spikes_pm_and_drops_gas_resistance():
    m = EnvModel(1)
    m.reset(at(17))
    quiet_pm, clean_gas = m.pm25, m.gas_ohm
    m.advance_to(at(18.4))
    assert m.pm25 > quiet_pm + 40
    assert m.gas_ohm < clean_gas * 0.7
    assert m.pm1 < m.pm25 < m.pm10


def test_magnus_roundtrip():
    assert rh_from_abs(9.2, 21.0) == pytest.approx(50.0, abs=1.5)


def test_reading_has_every_key_in_readings_md():
    m = EnvModel(2)
    m.reset(at(19))
    m.advance_to(at(20))
    d = reading_from(m)
    expected = {"ts", "device", "temp_c", "rh_pct", "co2_ppm", "pm1_0", "pm2_5", "pm10",
                "pc_0_3", "pc_0_5", "pc_1_0", "pc_2_5", "pc_5_0", "pc_10",
                "gas_ohm", "pressure_hpa", "iaq", "iaq_accuracy", "scd41", "bme688", "valid"}
    assert set(d) == expected
    assert set(d["scd41"]) == set(d["bme688"]) == {"temp_c", "rh_pct"}
    assert d["valid"] == {"temp_humidity": True, "co2": True, "particulates": True,
                          "pressure": True, "gas": True}
    json.dumps(d)  # serialisable


def test_reading_quirks_match_the_firmware_mocks():
    m = EnvModel(2)
    m.reset(at(19))
    m.advance_to(at(20))
    d = reading_from(m)
    assert d["bme688"]["temp_c"] == pytest.approx(d["temp_c"] + 1.5, abs=0.4)
    assert d["bme688"]["rh_pct"] < d["rh_pct"]
    assert d["scd41"]["temp_c"] == pytest.approx(d["temp_c"], abs=0.4)   # default offset cancels self-heating
    assert 0 <= d["iaq"] <= 500
    assert 1000 < d["pressure_hpa"] < 1025


def test_source_datasets_and_history_shape():
    src = MockReadingsSource(seed=7, now=lambda: at(21) + 30)
    ds = src.datasets()
    assert set(ds) == {"latest", "history_24h"}
    latest = ds["latest"]()
    assert latest["ts"] == at(21) + 30
    hist = ds["history_24h"]()
    assert len(hist) == 24 * 60 + 1
    assert hist[0]["ts"] == at(21) - 24 * 3600
    assert hist[-1]["ts"] == at(21)
    assert all(hist[i]["ts"] < hist[i + 1]["ts"] for i in range(len(hist) - 1))


def test_history_shows_the_evening_co2_rise():
    src = MockReadingsSource(seed=7, now=lambda: at(22))
    hist = src.history(6)                                  # 16:00 .. 22:00
    by_hour = {h["ts"]: h["co2_ppm"] for h in hist}
    assert by_hour[at(21)] > by_hour[at(17)] + 150
