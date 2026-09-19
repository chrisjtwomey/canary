"""The readings store: what the board posts, kept and served to the pages."""
import pytest
from bs4 import BeautifulSoup

from epd_server import DisplayServer, ReadingsStore

from server import make_pages, make_source
from sources.readings import ReadingsIngest, measurements
from sources.status import DeviceReports
from tests.conftest import AT
from tests.html import one

DOC = {"ts": AT, "device": "canary-dock", "co2_ppm": 812, "pressure_hpa": 1011.2,
       "valid": {"co2": True, "pressure": True},
       "client": {"board": "Inkplate5V2", "sensors": {"scd41": True}},
       "calibration": {"bme688": {"state": "AAEC", "accuracy": 3, "saved": AT - 60}}}


@pytest.fixture
def store(tmp_path):
    s = ReadingsStore(tmp_path / "readings.db")
    yield s
    s.close()


def test_a_document_with_no_measurements_is_not_a_reading(store):
    """The head posts its own state and no readings."""
    reports = DeviceReports(now=lambda: float(AT))
    ingest = ReadingsIngest(reports, store)
    ingest.accept({"ts": AT, "device": "canary-head", "client": {"rssi": -55}})
    assert store.count() == 0
    assert reports.device("canary-head")["doc"]["client"] == {"rssi": -55}


def test_measurements_leave_out_what_describes_the_board():
    kept = measurements(DOC)
    assert "client" not in kept and "calibration" not in kept
    assert kept == {k: v for k, v in DOC.items() if k not in ("client", "calibration")}


def test_the_store_gets_the_measurements_and_diagnostics_the_whole_report(store):
    reports = DeviceReports(now=lambda: float(AT))
    ReadingsIngest(reports, store).accept(DOC)
    assert reports.latest == DOC
    assert store.latest() == measurements(DOC)


def test_a_bad_document_reaches_neither(store):
    reports = DeviceReports()
    with pytest.raises(ValueError, match="ts"):
        ReadingsIngest(reports, store).accept({"device": "x"})
    assert reports.latest is None and store.count() == 0


def test_keep_days_deletes_older_readings_as_new_ones_arrive(store):
    ingest = ReadingsIngest(DeviceReports(), store, keep_days=1, now=lambda: float(AT))
    ingest.accept(dict(DOC, ts=AT - 2 * 86400))
    ingest.accept(dict(DOC, ts=AT - 3600))
    assert [d["ts"] for d in store.between(0)] == [AT - 3600]


def test_without_a_store_only_the_newest_report_is_kept():
    reports = DeviceReports()
    ReadingsIngest(reports).accept(DOC)
    assert reports.latest == DOC


def test_with_a_store_the_pages_read_what_the_board_posted(store):
    for minutes in range(180):
        store.add(dict(measurements(DOC), ts=AT - minutes * 60, co2_ppm=600 + minutes))
    ds = make_source(7, lambda: AT, DeviceReports(), altitude_m=10, store=store).datasets()

    latest = ds["latest"]()
    assert latest["ts"] == AT and latest["co2_ppm"] == 600
    assert latest["pressure_station_hpa"] == 1011.2 and latest["pressure_hpa"] > 1011.2
    history = ds["history_24h"]()
    assert history[0]["ts"] == AT - 179 * 60 and history[-1]["ts"] == AT
    assert {"latest", "history_24h", "history_72h", "status"} <= set(ds)


def test_before_the_first_reading_every_page_says_so(store, tz):
    ds = make_source(7, lambda: AT, DeviceReports(), altitude_m=10, store=store).datasets()
    data = {name: fetch() for name, fetch in ds.items()}
    assert data["latest"] is None

    for page in make_pages(tz, width=1280, height=720):
        page.template(**{name: data[name] for name in page.requires})
        soup = BeautifulSoup(str(page.airium), "html.parser")
        if "latest" in page.requires:
            assert one(soup, ".page-waiting .verdict").get_text() == "No readings yet.", page.name
        else:
            assert one(soup, ".verdict").get_text() == "No report from either board yet.", page.name


def test_a_posted_reading_reaches_the_pages_through_the_server(store, tz):
    reports = DeviceReports(now=lambda: float(AT))
    pages = make_pages(tz, width=1280, height=720)
    server = DisplayServer(pages=pages, source=make_source(7, lambda: AT, reports, store=store),
                           schedule=[("00:00:00", "breathe.png")], tz=tz,
                           ingest={"readings": ReadingsIngest(reports, store).accept})
    client = server._build_app().test_client()

    assert client.post("/readings", json=DOC).status_code == 204
    assert client.post("/readings", json=DOC).status_code == 204   # sent again after a lost reply
    assert store.count() == 1

    breathe = next(p for p in pages if p.name == "breathe")
    ds = server.source.datasets()
    breathe.template(**{name: ds[name]() for name in breathe.requires})
    soup = BeautifulSoup(str(breathe.airium), "html.parser")
    assert one(soup, "#co2 .value").get_text() == "812"
