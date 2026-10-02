"""The Comfort page's two boxes: config.yaml's comfort block, the guides they
draw, and the drawing that sets them on the Settings page."""
import pytest
from epd_server.config import ConfigError

from metrics import Comfort
from pages.pool import comfort_metrics
from server import load_comfort, make_between, make_history
from tests.conftest import AT, TZ
from web import HistoryQuery

WARMER = Comfort(temp=(24.0, 26.0), acceptable_temp=(20.0, 28.0))


def test_without_a_comfort_block_the_boxes_are_the_defaults():
    assert load_comfort({}) == Comfort((19, 24), (35, 60), (17, 26), (30, 65))


def test_a_comfort_block_sets_the_edges_it_names():
    c = load_comfort({"comfort": {"temp_from": 24, "temp_to": 26, "acceptable_temp_from": 20,
                                  "acceptable_temp_to": 28}})
    assert c == WARMER
    assert load_comfort({"comfort": {"temp_from": 22.5}}).temp == (22.5, 24.0)


@pytest.mark.parametrize("block, words", [
    ({"temp_to": 19}, "comfort.temp_to must be above comfort.temp_from"),
    ({"acceptable_rh_from": 70}, "comfort.acceptable_rh_to must be above comfort.acceptable_rh_from"),
    ({"acceptable_temp_from": 20}, "comfort.acceptable_temp_from must be at or below comfort.temp_from"),
    ({"rh_to": 70}, "comfort.acceptable_rh_to must be at or above comfort.rh_to"),
    ({"temp_from": "cool"}, "comfort.temp_from must be a number"),
])
def test_boxes_that_cannot_work_are_refused(block, words):
    with pytest.raises(ConfigError, match=f"^{words}$"):
        load_comfort({"comfort": block})


def test_the_traces_draw_the_inner_box():
    temp, rh = comfort_metrics(WARMER)
    assert temp.guides == ((24.0, "cool"), (26.0, "warm"))
    assert rh.guides == ((35.0, "dry"), (60.0, "humid"))
    assert temp.level_words(21.2) == "Cool."


def test_the_explorer_draws_a_person_s_edges():
    history = HistoryQuery(make_history(make_between(7, lambda: AT)), TZ, now=lambda: AT,
                           comfort=WARMER)
    guides = history.answer({"metric": "temperature"})["spec"]["guides"]
    assert [(g["y"], g["label"]) for g in guides] == [(24.0, "cool"), (26.0, "warm")]
