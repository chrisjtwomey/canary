"""The board's reports: accepted by POST, served as the status dataset."""
import pytest
from bs4 import BeautifulSoup

from epd_server import DisplayServer
from server import make_pages, make_source
from sources.status import DeviceReports, StatusSource
from tests.conftest import AT


def test_accept_keeps_the_newest_and_counts():
    reports = DeviceReports(now=lambda: 1000.0)
    reports.accept({"ts": 1})
    reports.accept({"ts": 2, "device": "x"})
    assert reports.latest == {"ts": 2, "device": "x"}
    assert reports.count == 2 and reports.received == 1000.0


@pytest.mark.parametrize("doc", [{}, {"ts": "x"}, {"ts": True}, {"ts": 1.5}])
def test_accept_rejects_a_missing_or_wrong_ts(doc):
    with pytest.raises(ValueError, match="ts"):
        DeviceReports().accept(doc)


def test_status_dataset_is_none_then_carries_the_age():
    clock = [1000.0]
    reports = DeviceReports(now=lambda: clock[0])
    status = StatusSource(reports).datasets()["status"]
    assert status() is None
    reports.accept({"ts": 5})
    clock[0] += 40
    assert status() == {"doc": {"ts": 5}, "age_s": 40, "count": 1}


def test_a_posted_report_reaches_the_diagnostics_page(tmp_path, tz):
    reports = DeviceReports(now=lambda: 1000.0)
    source = make_source(7, lambda: AT, reports)
    pages = make_pages(tz, width=1280, height=720)
    for p in pages:
        p.png_dir = str(tmp_path)
        p.html_dir = str(tmp_path / "static")
    server = DisplayServer(pages=pages, source=source, schedule=[("00:00:00", "breathe.png")],
                           tz=tz, ingest={"readings": reports.accept})
    client = server._build_app().test_client()

    rsp = client.post("/readings", json={
        "ts": AT, "device": "inkplate5-env-monitor", "valid": {"co2": True},
        "client": {"board": "Inkplate5V2", "ip": "192.168.1.35", "rssi": -61,
                   "sensors": {"scd41": True}},
    })
    assert rsp.status_code == 204

    diag = next(p for p in pages if p.name == "diagnostics")
    diag.template(status=source.datasets()["status"]())
    soup = BeautifulSoup(str(diag.airium), "html.parser")
    assert soup.select_one("#ip").get_text() == "192.168.1.35"
    assert soup.select_one("#rssi").get_text() == "-61 dBm, good"
    assert soup.select_one("#sensor-scd41").get_text() == "ok"
    assert soup.select_one("#sensor-shtc3").get_text() == "missing"
