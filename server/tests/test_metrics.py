from datetime import datetime

import pytest

from metrics import (co2_verdict, comfort_verdict, dew_point_c, extremes, fmt_int, fmt_stamp,
                     hour_ticks, night_spans, series, thin, y_range)
from tests.conftest import AT, TZ


def test_dew_point_matches_the_textbook_value():
    assert dew_point_c(20.0, 50.0) == pytest.approx(9.3, abs=0.1)
    assert dew_point_c(22.0, 100.0) == pytest.approx(22.0, abs=0.01)


@pytest.mark.parametrize("ppm, words", [
    (450, "Fresh air."),
    (699, "Fresh air."),
    (700, "Fresh enough."),
    (999, "Fresh enough."),
    (1000, "Getting stuffy."),
    (1500, "Stuffy. Open a window."),
    (2400, "Stale. Air the room."),
])
def test_co2_bands(ppm, words):
    assert co2_verdict(ppm) == words


@pytest.mark.parametrize("t, rh, words", [
    (21.0, 45.0, "Comfortable."),
    (25.0, 45.0, "Warm."),
    (25.0, 65.0, "Warm and humid."),
    (17.0, 30.0, "Cool and dry."),
    (21.0, 70.0, "Humid."),
    (21.0, 25.0, "Dry."),
])
def test_comfort_wording(t, rh, words):
    assert comfort_verdict(t, rh) == words


def docs(n, start=1000, step=60, **fields):
    return [{"ts": start + i * step, **fields} for i in range(n)]


def test_thin_keeps_one_document_per_interval():
    kept = thin(docs(11), 300)
    assert [d["ts"] for d in kept] == [1000, 1300, 1600]


def test_series_skips_documents_without_the_key():
    history = docs(3, co2_ppm=500)
    history[1] = {"ts": history[1]["ts"]}
    assert series(history, "co2_ppm") == [[1000, 500], [1120, 500]]


def test_extremes_returns_the_documents_and_handles_nothing():
    history = [{"ts": 1, "v": 5}, {"ts": 2, "v": 9}, {"ts": 3, "v": 2}]
    lo, hi = extremes(history, "v")
    assert (lo["ts"], hi["ts"]) == (3, 2)
    assert extremes([{"ts": 1}], "v") == (None, None)


def test_y_range_applies_floor_ceiling_and_padding():
    assert y_range([500, 900], floor=400, ceil=1200) == {"min": 400, "max": 1200}
    assert y_range([500, 1300], floor=400, ceil=1200) == {"min": 400, "max": 1300}
    assert y_range([20.0, 22.0], pad=1.0) == {"min": 19.0, "max": 23.0}
    assert y_range([], floor=0) == {"min": 0, "max": 1.0}


def test_hour_ticks_land_on_local_whole_hours():
    ticks = hour_ticks(AT - 24 * 3600, AT, TZ, every=6)
    assert [t["label"] for t in ticks] == ["00", "06", "12", "18"]
    for t in ticks:
        assert datetime.fromtimestamp(t["x"], TZ).minute == 0


def test_night_spans_are_clipped_to_the_window():
    spans = night_spans(AT - 24 * 3600, AT, TZ)
    assert len(spans) == 1
    a, b = spans[0]
    assert datetime.fromtimestamp(a, TZ).strftime("%H:%M") == "22:00"
    assert datetime.fromtimestamp(b, TZ).strftime("%H:%M") == "07:00"
    assert a >= AT - 24 * 3600 and b <= AT


def test_formatting():
    assert fmt_int(1240.6) == "1,241"
    assert fmt_stamp(AT, TZ) == "Thu 3 Sep, 21:45"


# ---------- the newer derived values ----------

from metrics import (abs_humidity_g_m3, barometer_word, fmt_bytes, fmt_duration, iaq_verdict,  # noqa: E402
                     local_midnight, minutes_above, pm25_verdict, pressure_tendency, rssi_quality,
                     tendency_words, value_at, ventilation_events)
from sources.mock import rh_from_abs  # noqa: E402


@pytest.mark.parametrize("ug, words", [
    (5, "Clean air."), (15, "Clean air."), (20, "Fine."), (30, "Some dust."),
    (45, "Dusty."), (60, "Bad air."), (100, "Very bad air."),
])
def test_pm25_bands_follow_who(ug, words):
    assert pm25_verdict(ug) == words


@pytest.mark.parametrize("iaq, words", [
    (10, "Excellent air."), (49, "Excellent air."), (50, "Good air."), (120, "A little stale."),
    (180, "Polluted."), (220, "Heavily polluted."), (300, "Severely polluted."), (400, "Extremely polluted."),
])
def test_iaq_bands_follow_bosch(iaq, words):
    assert iaq_verdict(iaq) == words


def test_absolute_humidity_is_the_inverse_of_the_mocks_rh():
    assert rh_from_abs(abs_humidity_g_m3(21.0, 45.0), 21.0) == pytest.approx(45.0, abs=0.01)
    assert abs_humidity_g_m3(20.0, 50.0) == pytest.approx(8.65, abs=0.1)


def test_value_at_takes_the_newest_document_within_slack():
    history = [{"ts": 1000, "v": 1}, {"ts": 1060, "v": 2}, {"ts": 1120, "v": 3}]
    assert value_at(history, "v", 1100) == 2
    assert value_at(history, "v", 1120) == 3
    assert value_at(history, "v", 5000) is None
    assert value_at(history, "v", 900) is None


def test_pressure_tendency_over_three_hours():
    start = 1_000_000
    history = [{"ts": start + i * 60, "pressure_hpa": 1010.0 + i * 0.05} for i in range(240)]
    latest = {"ts": start + 240 * 60, "pressure_hpa": 1022.0}
    assert pressure_tendency(history, latest) == pytest.approx(1022.0 - 1013.0, abs=0.01)
    assert pressure_tendency([], latest) is None


@pytest.mark.parametrize("delta, words", [
    (None, "No trend yet."), (4.0, "Rising fast."), (2.0, "Rising."), (0.5, "Steady."),
    (-0.5, "Steady."), (-2.0, "Falling."), (-5.0, "Falling fast."),
])
def test_tendency_words(delta, words):
    assert tendency_words(delta) == words


@pytest.mark.parametrize("hpa, word", [
    (970, "Stormy"), (990, "Rain"), (1010, "Change"), (1020, "Fair"), (1035, "Very dry"),
])
def test_barometer_legends(hpa, word):
    assert barometer_word(hpa) == word


def test_minutes_above_counts_per_minute_documents():
    history = [{"ts": 1000 + i * 60, "co2_ppm": v} for i, v in enumerate([900, 1100, 1200, 1000, 1300])]
    assert minutes_above(history, "co2_ppm", 1000, since=1000) == 3
    assert minutes_above(history, "co2_ppm", 1000, since=1000 + 4 * 60) == 1


def test_ventilation_events_find_the_evening_window_and_not_the_slow_decay(data, tz):
    events = ventilation_events(data["history_24h"])
    hours = [datetime.fromtimestamp(t, tz).hour + datetime.fromtimestamp(t, tz).minute / 60 for t in events]
    assert any(21.95 <= h <= 22.15 for h in hours), hours    # the window opens at 22:00 local
    assert any(8.95 <= h <= 9.1 for h in hours), hours       # and at 09:00
    assert not any(0.5 <= h <= 7.0 for h in hours), hours    # overnight decay is slow


def test_local_midnight(tz):
    assert datetime.fromtimestamp(local_midnight(AT, tz), tz).strftime("%Y-%m-%d %H:%M") == "2026-09-03 00:00"


@pytest.mark.parametrize("dbm, expected", [
    (-50, (4, "strong")), (-60, (3, "good")), (-70, (2, "fair")), (-80, (1, "weak")), (-90, (0, "none")),
])
def test_rssi_quality(dbm, expected):
    assert rssi_quality(dbm) == expected


@pytest.mark.parametrize("seconds, text", [
    (45, "45 s"), (90, "1 min"), (3600, "1 h"), (8040, "2 h 14 min"), (90000, "1 d 1 h"),
])
def test_fmt_duration(seconds, text):
    assert fmt_duration(seconds) == text


def test_fmt_bytes():
    assert fmt_bytes(120000) == "117 KB"
    assert fmt_bytes(4194304) == "4.0 MB"
