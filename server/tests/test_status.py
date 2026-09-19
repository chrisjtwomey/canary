"""The board's reports: accepted by POST, served as the status dataset."""
import pytest
from bs4 import BeautifulSoup

from tests.html import one

from epd_server import DisplayServer, ReadingsStore
from server import make_pages, make_source
from sources.status import DeviceReports, StatusSource
from tests.conftest import AT


def test_accept_keeps_the_newest_and_counts():
    reports = DeviceReports(now=lambda: 1000.0)
    reports.accept({"ts": 1})
    reports.accept({"ts": 2, "device": "x"})
    assert reports.latest == {"ts": 2, "device": "x"}
    assert reports.count == 2 and reports.received == 1000.0


def test_each_board_keeps_its_own_newest_report():
    reports = DeviceReports(now=lambda: 1000.0)
    reports.accept({"ts": 10, "device": "canary-dock", "co2_ppm": 700})
    reports.accept({"ts": 11, "device": "canary-head", "client": {"ip": "192.168.1.9"}})
    assert reports.device("canary-dock")["doc"]["co2_ppm"] == 700
    assert reports.device("canary-head")["doc"]["client"]["ip"] == "192.168.1.9"
    assert reports.devices() == ["canary-head", "canary-dock"]
    assert reports.device("canary-shed") is None


def test_reports_are_kept_in_the_store_and_pruned(tmp_path):
    clock = [10 * 86400.0]
    store = ReadingsStore(tmp_path / "status.db")
    reports = DeviceReports(now=lambda: clock[0], store=store, keep_days=1)
    reports.accept({"ts": 8 * 86400, "device": "canary-head", "client": {"rssi": -60}})
    reports.accept({"ts": 10 * 86400, "device": "canary-head", "client": {"rssi": -55}})
    reports.accept({"ts": 10 * 86400, "device": "canary-dock", "co2_ppm": 700,
                    "client": {"rssi": -70}})
    # The one from two days ago is past keep_days; each board's newest stays.
    assert store.count() == 2
    assert store.latest("canary-head")["client"] == {"rssi": -55}
    # Measurements stay out of the report: they have a store of their own.
    assert store.latest("canary-dock") == {"ts": 10 * 86400, "device": "canary-dock",
                                           "client": {"rssi": -70}}


def test_a_report_without_a_client_block_is_not_stored(tmp_path):
    store = ReadingsStore(tmp_path / "status.db")
    reports = DeviceReports(now=lambda: 1000.0, store=store)
    reports.accept({"ts": 10, "device": "canary-dock", "co2_ppm": 700})
    assert store.count() == 0


def test_a_held_reading_arriving_late_does_not_replace_the_newest():
    reports = DeviceReports(now=lambda: 1000.0)
    reports.accept({"ts": 10, "client": {"ip": "192.168.1.42"}})
    reports.accept({"ts": 5, "co2_ppm": 700})
    assert reports.latest == {"ts": 10, "client": {"ip": "192.168.1.42"}}
    assert reports.count == 2


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
    assert status() == {"doc": {"ts": 5}, "age_s": 40, "count": 1,
                        "boards": {"": {"doc": {"ts": 5}, "age_s": 40}}}


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
        "ts": AT, "device": "canary-dock", "valid": {"co2": True},
        "client": {"board": "Inkplate5V2", "ip": "192.168.1.42", "rssi": -61,
                   "sensors": {"scd41": True}},
    })
    assert rsp.status_code == 204

    diag = next(p for p in pages if p.name == "diagnostics")
    diag.template(status=source.datasets()["status"]())
    soup = BeautifulSoup(str(diag.airium), "html.parser")
    assert one(soup, "#dock-ip").get_text() == "192.168.1.42"
    assert one(soup, "#dock-rssi").get_text() == "-61 dBm, good"
    assert one(soup, "#dock-sensor-scd41").get_text() == "ok"
    assert one(soup, "#dock-sensor-shtc3").get_text() == "missing"


def test_status_history_groups_the_stored_reports_by_board(tmp_path):
    clock = [10 * 86400.0]
    store = ReadingsStore(tmp_path / "status.db")
    reports = DeviceReports(now=lambda: clock[0], store=store)
    for i in range(3):
        reports.accept({"ts": int(clock[0]) - 3600 * i, "device": "canary-head", "client": {"rssi": -60 - i}})
    reports.accept({"ts": int(clock[0]) - 30 * 3600, "device": "canary-head", "client": {"rssi": -90}})
    reports.accept({"ts": int(clock[0]), "device": "canary-dock", "client": {"rssi": -70}})
    history = StatusSource(reports).datasets()["status_history_24h"]()
    assert [d["client"]["rssi"] for d in history["canary-head"]] == [-62, -61, -60]   # oldest first, yesterday's out
    assert [d["client"]["rssi"] for d in history["canary-dock"]] == [-70]
    assert StatusSource(DeviceReports()).datasets()["status_history_24h"]() == {}
