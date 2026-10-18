import dataclasses
from datetime import datetime

import pytest

from dock_settings import DockSettings
from metrics import COMFORT
from urgency import FAST, OVER, Prioritiser, urgent

NOW = 1_790_000_000
ALL = {"breathe.png", "co2-delta.png", "co2-trace.png", "comfort.png", "comfort-delta.png",
       "comfort-trace.png", "dust.png", "dust-delta.png", "dust-trace.png", "air.png",
       "air-delta.png", "air-trace.png", "barometer-delta.png", "barometer-trace.png", "day.png"}
VALID = {"co2": True, "temp_humidity": True, "particulates": True, "gas": True, "pressure": True}
CALM = {"co2_ppm": 600, "temp_c": 21.0, "rh_pct": 45, "pm2_5": 3, "static_iaq": 30,
        "static_iaq_accuracy": 3, "pressure_hpa": 1015.0}


def room(**now):
    """The newest reading, with ``now`` over a calm room."""
    return {"ts": NOW, "valid": VALID, **CALM, **now}


def calm_history(steady=None, **then):
    """A reading every 5 minutes for the last 2 hours: the calm room with
    ``steady`` all along, and ``then`` in the one 15 minutes back."""
    docs = [{"ts": NOW - s, **CALM, **(steady or {})} for s in range(7200, 0, -300)]
    for d in docs:
        if d["ts"] == NOW - 900:
            d.update(then)
    return docs


def found(latest, history=None, alerts=DockSettings()):
    """What is urgent; without ``history``, the room held ``latest`` all along."""
    if history is None:
        history = calm_history({k: v for k, v in latest.items() if k in CALM})
    return [(u.measurement.name, u.level, u.delta_first)
            for u in urgent(latest, history, alerts, COMFORT)]


@pytest.mark.parametrize("now, expected", [
    ({"co2_ppm": 1500}, [("co2", OVER, False)]),
    ({"co2_ppm": 1499}, []),
    ({"pm2_5": 37.5}, [("dust", OVER, False)]),
    ({"pm2_5": 37}, []),
    ({"static_iaq": 150}, [("air", OVER, False)]),
    ({"static_iaq": 149}, []),
    ({"temp_c": 27.0}, [("comfort", OVER, False)]),
    ({"temp_c": 25.0}, []),
    ({"rh_pct": 70}, [("comfort", OVER, False)]),
    ({"rh_pct": 62}, []),
])
def test_a_value_at_or_over_its_limit_is_urgent_and_one_close_to_it_is_not(now, expected):
    assert found(room(**now)) == expected


def test_the_alert_thresholds_come_from_the_dock_settings():
    alerts = dataclasses.replace(DockSettings(), scd41_poor_air_ppm=1200)
    assert found(room(co2_ppm=1250), alerts=alerts) == [("co2", OVER, False)]


def test_an_air_quality_index_still_calibrating_has_no_limit():
    assert found(room(static_iaq=180, static_iaq_accuracy=2)) == []


def test_a_reading_that_is_not_valid_is_never_urgent():
    assert found(room(co2_ppm=2000, valid={**VALID, "co2": False})) == []
    assert found({}) == []


@pytest.mark.parametrize("now, then, expected", [
    ({"co2_ppm": 780}, {"co2_ppm": 600}, [("co2", FAST, True)]),
    ({"co2_ppm": 480}, {"co2_ppm": 600}, [("co2", FAST, True)]),
    ({"co2_ppm": 700}, {"co2_ppm": 600}, []),
    ({"pressure_hpa": 1013.5}, {}, [("barometer", FAST, True)]),
])
def test_a_fast_change_up_or_down_is_urgent(now, then, expected):
    history = calm_history(**then)
    if "pressure_hpa" in now:
        for d in history:
            if d["ts"] == NOW - 3600:
                d["pressure_hpa"] = 1015.0
    assert found(room(**now), history) == expected


def test_over_its_limit_starts_on_the_main_page_even_when_fast():
    assert found(room(co2_ppm=1600), calm_history(co2_ppm=1400)) == [("co2", OVER, False)]


def test_a_fast_humidity_starts_on_the_main_page_since_the_delta_page_shows_temperature():
    assert found(room(rh_pct=55), calm_history(rh_pct=45)) == [("comfort", FAST, False)]


def test_the_most_urgent_comes_first():
    assert [n for n, _, _ in found(room(co2_ppm=1000, pm2_5=40, temp_c=22.0),
                                   calm_history({"pm2_5": 40}, co2_ppm=800,
                                                temp_c=21.0))] == ["dust", "co2", "comfort"]


# ── The turn ─────────────────────────────────────────────────────────

WAKE = datetime(2026, 10, 18, 12, 0)


def picks(chooser, slots, scheduled="day.png"):
    return [chooser.choose(scheduled, WAKE) for _ in range(slots)]


def chooser(latest, shown=ALL, history=None, keep=frozenset()):
    steady = calm_history({k: v for k, v in latest.items() if k in CALM})
    data = {"latest": latest, "history": history or steady}
    c = Prioritiser(lambda: (data["latest"], data["history"]), shown, DockSettings(), COMFORT,
                    keep=keep)
    return c, data


def test_one_urgent_measurement_shows_its_pages_then_one_scheduled_page_in_turn():
    c, _ = chooser(room(co2_ppm=1600))
    assert picks(c, 8) == ["breathe.png", "co2-delta.png", "co2-trace.png", "day.png",
                           "breathe.png", "co2-delta.png", "co2-trace.png", "day.png"]


def test_a_fast_change_starts_on_its_delta_page():
    c, _ = chooser(room(co2_ppm=780), history=calm_history(co2_ppm=600))
    assert picks(c, 4) == ["co2-delta.png", "breathe.png", "co2-trace.png", "day.png"]


def test_two_urgent_measurements_take_turns_most_urgent_first():
    c, _ = chooser(room(co2_ppm=1000, pm2_5=40),
                   history=calm_history({"pm2_5": 40}, co2_ppm=800))
    assert picks(c, 7) == ["dust.png", "co2-delta.png", "dust-delta.png", "breathe.png",
                           "dust-trace.png", "co2-trace.png", "day.png"]


def test_only_pages_in_the_pools_show():
    c, _ = chooser(room(co2_ppm=1600, pm2_5=40), shown={"breathe.png", "co2-trace.png", "day.png"})
    assert picks(c, 3) == ["breathe.png", "co2-trace.png", "day.png"]


def test_a_kept_page_is_never_replaced():
    c, _ = chooser(room(co2_ppm=1600), keep={"splash.png"})
    assert picks(c, 2, scheduled="splash.png") == ["splash.png", "splash.png"]


def test_a_change_in_what_is_urgent_starts_the_turn_again():
    c, data = chooser(room(co2_ppm=1600))
    assert picks(c, 2) == ["breathe.png", "co2-delta.png"]
    data["latest"] = room(co2_ppm=1600, pm2_5=40)
    data["history"] = calm_history({"co2_ppm": 1600, "pm2_5": 40})
    assert picks(c, 2) == ["breathe.png", "dust.png"]
    data["latest"], data["history"] = room(), calm_history()
    assert picks(c, 2) == ["day.png", "day.png"]


# ── The setting ──────────────────────────────────────────────────────

def test_prioritise_alerts_is_on_by_default_and_never_reaches_epd():
    from epd_server.config import ConfigError
    from server import DEFAULT_DISPLAY, epd_config, load_settings
    zone = {"server": {"timezone": "Europe/Dublin"}}

    assert load_settings(zone).prioritise_alerts is True
    off = {**zone, "display": {**DEFAULT_DISPLAY, "prioritise_alerts": False,
                               "sync": {"every": 600}}}
    assert load_settings(off).prioritise_alerts is False
    assert epd_config(off)["display"] == DEFAULT_DISPLAY
    with pytest.raises(ConfigError, match="^display.prioritise_alerts must be true or false$"):
        load_settings({**zone, "display": {**DEFAULT_DISPLAY, "prioritise_alerts": "yes"}})
