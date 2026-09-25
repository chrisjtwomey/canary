"""The board's reports: accepted by POST, served as the status dataset."""
import sys
import threading

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


def test_a_restart_brings_back_each_boards_newest_report(tmp_path):
    """The store outlives the server, so the pages need not wait for each
    board to post again before they have something to show."""
    store = ReadingsStore(tmp_path / "status.db")
    before = DeviceReports(now=lambda: 2000.0, store=store)
    before.accept({"ts": 1000, "device": "canary-dock", "client": {"rssi": -70}})
    before.accept({"ts": 1600, "device": "canary-dock", "client": {"rssi": -65}})
    before.accept({"ts": 1500, "device": "canary-head", "client": {"rssi": -60}})

    after = DeviceReports(now=lambda: 2000.0, store=store)
    assert after.devices() == ["canary-dock", "canary-head"]
    assert after.device("canary-dock") == {"doc": {"ts": 1600, "device": "canary-dock",
                                                    "client": {"rssi": -65}}, "age_s": 400}
    assert after.device("canary-head")["age_s"] == 500
    assert after.count == 3


def test_a_restart_brings_back_nothing_the_store_has_pruned(tmp_path):
    store = ReadingsStore(tmp_path / "status.db")
    DeviceReports(now=lambda: 100.0, store=store).accept(
        {"ts": 100, "device": "canary-head", "client": {}})
    after = DeviceReports(now=lambda: 3 * 86400.0, store=store, keep_days=1)
    assert after.devices() == [] and after.latest is None


def test_a_report_without_a_client_block_is_not_stored(tmp_path):
    store = ReadingsStore(tmp_path / "status.db")
    reports = DeviceReports(now=lambda: 1000.0, store=store)
    reports.accept({"ts": 10, "device": "canary-dock", "co2_ppm": 700})
    assert store.count() == 0


def test_a_report_the_store_already_holds_is_not_counted(tmp_path):
    store = ReadingsStore(tmp_path / "status.db")
    reports = DeviceReports(store=store)
    doc = {"ts": 10, "device": "canary-dock", "client": {"rssi": -60}}
    assert reports.accept_many([doc, {"ts": 11, "device": "canary-dock", "client": {}}]) == [True, True]
    assert reports.accept_many([doc]) == [False]
    assert reports.count == 2 and store.count() == 1
    store.close()


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
                           tz=tz, ingest={"sensor-readings": reports.accept_many})
    client = server._build_app().test_client()

    rsp = client.post("/sensor-readings", json={
        "ts": AT, "device": "canary-dock", "valid": {"co2": True},
        "client": {"board": "Inkplate5V2", "ip": "192.168.1.42", "rssi": -61,
                   "dock": {"sensors": {"scd41": True}}},
    })
    assert rsp.status_code == 200 and rsp.get_json() == [True]

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


def test_a_board_with_sync_slots_says_when_its_next_is():
    reports = DeviceReports(now=lambda: 1000.0,
                            next_sync=lambda device, now: 120 if device == "canary-dock" else None)
    reports.accept({"ts": 1, "device": "canary-dock", "client": {"rssi": -60}})
    reports.accept({"ts": 1, "device": "canary-head", "client": {"rssi": -60}})
    assert reports.device("canary-dock")["next_sync_s"] == 120
    assert "next_sync_s" not in reports.device("canary-head")


def test_a_refused_board_is_known_before_any_report_is_taken():
    clock = [1000.0]
    reports = DeviceReports(now=lambda: clock[0])
    reports.refused("canary-dock", "v0.4.0")
    clock[0] = 1030.0
    reports.refused("canary-dock", "v0.4.0")
    source = StatusSource(reports)

    status = source.status()
    assert status["doc"] is None and status["count"] == 0
    dock = status["boards"]["canary-dock"]
    assert dock["doc"] is None and dock["refused"] == {
        "version": "v0.4.0", "count": 2, "at": 1030.0, "age_s": 0}


def test_a_report_from_the_new_version_clears_the_refusal():
    reports = DeviceReports(now=lambda: 1000.0)
    reports.accept({"ts": 1, "device": "canary-dock", "client": {"version": "v0.4.0"}})
    reports.refused("canary-dock", "v0.4.0")
    reports.accept({"ts": 2, "device": "canary-dock", "client": {"version": "v0.4.0"}})
    assert "refused" in reports.device("canary-dock"), "the same version is still refused"
    reports.accept({"ts": 3, "device": "canary-dock", "client": {"version": "v0.3.1"}})
    assert "refused" not in reports.device("canary-dock")


def test_the_server_tells_the_reports_which_board_it_refused(tmp_path, tz):
    reports = DeviceReports(now=lambda: 1000.0)
    server = DisplayServer(pages=make_pages(tz, width=1280, height=720),
                           source=make_source(7, lambda: AT, reports),
                           schedule=[("00:00:00", "breathe.png")], tz=tz,
                           ingest={"sensor-readings": reports.accept_many}, header_prefix="Canary",
                           server_version="v0.3.1", version_gate=True, on_refused=reports.refused)
    client = server._build_app().test_client()

    rsp = client.post("/sensor-readings", json={"ts": AT, "device": "canary-dock"},
                      headers={"Canary-Device": "canary-dock", "Canary-Device-Version": "v0.4.0"})

    assert rsp.status_code == 409
    assert reports.device("canary-dock")["refused"]["version"] == "v0.4.0"


def test_the_health_object_is_kept_beside_the_client_one(tmp_path):
    store = ReadingsStore(tmp_path / "status.db")
    reports = DeviceReports(store=store)
    reports.accept({"ts": 10, "device": "canary-dock", "co2_ppm": 700,
                    "client": {"rssi": -60}, "health": {"restarts": 1}})
    assert store.latest() == {"ts": 10, "device": "canary-dock", "client": {"rssi": -60},
                              "health": {"restarts": 1}}
    store.close()


def _silence(device, now):
    return 600 if device == "canary-dock" else 120


@pytest.mark.parametrize("age, offline", [(600 + 60, False), (600 + 61, True)])
def test_a_board_that_has_missed_two_posts_is_offline(age, offline):
    clock = [10_000.0]
    reports = DeviceReports(now=lambda: clock[0], silence=_silence)
    reports.accept({"ts": 10_000, "device": "canary-dock", "client": {"ip": "x"}})
    clock[0] += age

    assert reports.device("canary-dock")["offline"] is offline


def test_no_board_is_judged_without_the_rule():
    reports = DeviceReports(now=lambda: 10_000.0)
    reports.accept({"ts": 1, "device": "canary-dock", "client": {"ip": "x"}})

    assert "offline" not in reports.device("canary-dock")


def test_reports_from_several_threads_at_once_are_all_counted():
    """The server answers each request on its own thread."""
    before = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)     # switch threads as often as possible
    reports = DeviceReports(now=lambda: 1e9)
    status = StatusSource(reports)
    errors = []

    def post(board):
        for ts in range(2000):
            reports.accept({"ts": ts, "device": f"{board}-{ts % 50}", "client": {}})

    def read():
        for _ in range(500):
            try:
                status.status()
            except Exception as exc:    # noqa: BLE001 - any failure is the finding
                errors.append(exc)

    try:
        threads = [threading.Thread(target=post, args=(b,)) for b in ("a", "b", "c")]
        threads.append(threading.Thread(target=read))
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(before)

    assert errors == []
    assert reports.count == 6000
    assert len(reports.devices()) == 150
