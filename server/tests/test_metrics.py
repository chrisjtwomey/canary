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
