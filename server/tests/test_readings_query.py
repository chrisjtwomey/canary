"""Reading back what the boards posted: GET /sensor-readings and GET /status."""
import pytest

from epd_server import DisplayServer, ReadingsStore

from server import make_between, make_pages, make_source
from sources.readings import MAX_READINGS, ReadingsIngest, ReadingsQuery
from sources.status import DeviceReports, StatusSource
from tests.conftest import AT

DOCK = {"ts": AT, "device": "canary-dock", "co2_ppm": 812, "valid": {"co2": True},
        "client": {"board": "canary-dock", "sensors": {"scd41": True}}}
HEAD = {"ts": AT + 30, "device": "canary-head", "client": {"board": "Inkplate5V2", "rssi": -55}}


@pytest.fixture
def store(tmp_path):
    s = ReadingsStore(tmp_path / "sensor-readings.db")
    yield s
    s.close()


@pytest.fixture
def client(store, tz):
    reports = DeviceReports(now=lambda: float(AT + 60))
    status = StatusSource(reports)
    server = DisplayServer(
        pages=make_pages(tz, width=1280, height=720),
        source=make_source(7, lambda: AT, reports, store=store),
        schedule=[("00:00:00", "breathe.png")], tz=tz,
        ingest={"sensor-readings": ReadingsIngest(reports, store).accept},
        queries={"sensor-readings": ReadingsQuery(make_between(7, lambda: AT, store),
                                           now=lambda: AT + 60).answer,
                 "status": lambda args: status.status()})
    return server.app.test_client()


def test_a_posted_reading_comes_back_as_it_was_stored(client):
    client.post("/sensor-readings", json=[dict(DOCK, ts=AT - 300, co2_ppm=790), DOCK, HEAD])
    answer = client.get("/sensor-readings").get_json()
    assert answer["count"] == 2 and answer["left_out"] == 0
    assert answer["readings"][1] == {k: v for k, v in DOCK.items() if k != "client"}
    assert [d["co2_ppm"] for d in answer["readings"]] == [790, 812]


def test_the_window_and_the_board_narrow_it(client):
    client.post("/sensor-readings", json=[dict(DOCK, ts=AT - 7200), DOCK,
                                   dict(DOCK, ts=AT - 60, device="canary-other")])
    got = client.get(f"/sensor-readings?from={AT - 3600}&to={AT}&device=canary-dock").get_json()
    assert [d["ts"] for d in got["readings"]] == [AT]
    assert (got["from"], got["to"]) == (AT - 3600, AT)


@pytest.mark.parametrize("query", ["from=yesterday", f"from={AT}&to={AT - 1}"])
def test_a_bad_window_is_a_400(client, query):
    assert client.get("/sensor-readings?" + query).status_code == 400


def test_a_long_answer_keeps_the_newest(tz):
    docs = [{"ts": t, "device": "canary-dock"} for t in range(MAX_READINGS + 3)]
    answer = ReadingsQuery(lambda start, end: docs, now=lambda: MAX_READINGS).answer({"from": "0"})
    assert answer["count"] == MAX_READINGS and answer["left_out"] == 3
    assert answer["readings"][0]["ts"] == 3


def test_status_is_each_boards_newest_report(client):
    assert client.get("/status").status_code == 404
    client.post("/sensor-readings", json=[DOCK, HEAD])
    status = client.get("/status").get_json()
    assert status["doc"]["device"] == "canary-head"
    assert status["boards"]["canary-dock"]["doc"]["client"]["sensors"] == {"scd41": True}
    assert status["boards"]["canary-head"]["age_s"] == 0   # since it arrived, not since its ts
