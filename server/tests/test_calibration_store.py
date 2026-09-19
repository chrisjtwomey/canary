"""The board's calibration copies: kept, pruned, and handed back."""
import pytest

from epd_server import DisplayServer, ReadingsStore

from server import make_pages, make_source
from sources.calibration import CalibrationStore
from sources.readings import ReadingsIngest
from sources.status import DeviceReports
from tests.conftest import AT

DEVICE = "canary-dock"


def copy(saved, accuracy=3, state="AAEC"):
    return {"bme688": {"state": state, "accuracy": accuracy, "saved": saved}}


@pytest.fixture
def cal(tmp_path):
    s = CalibrationStore(tmp_path / "calibration.db", keep_days=3, now=lambda: float(AT))
    yield s
    s.close()


def client_for(cal, tz):
    reports = DeviceReports(now=lambda: float(AT))
    server = DisplayServer(pages=make_pages(tz, width=1280, height=720),
                           source=make_source(7, lambda: AT, reports),
                           schedule=[("00:00:00", "breathe.png")], tz=tz,
                           ingest={"readings": ReadingsIngest(reports, calibration=cal).accept},
                           queries={"calibration": cal.answer})
    return server._build_app().test_client()


def test_the_newest_copy_saved_before_the_time_is_handed_back(cal):
    for saved in (AT - 7200, AT - 3600, AT - 60):
        cal.add(DEVICE, copy(saved, state=f"S{saved}"))
    assert cal.lookup(DEVICE, before=AT - 1800) == copy(AT - 3600, state=f"S{AT - 3600}")


def test_a_copy_at_accuracy_3_wins_over_a_newer_one_below_it(cal):
    cal.add(DEVICE, copy(AT - 7200, accuracy=3, state="high"))
    cal.add(DEVICE, copy(AT - 600, accuracy=1, state="low"))
    assert cal.lookup(DEVICE, before=AT)["bme688"]["state"] == "high"


def test_without_a_copy_at_3_the_newest_is_handed_back(cal):
    cal.add(DEVICE, copy(AT - 7200, accuracy=1, state="older"))
    cal.add(DEVICE, copy(AT - 600, accuracy=2, state="newer"))
    assert cal.lookup(DEVICE, before=AT)["bme688"]["state"] == "newer"


def test_copies_made_since_the_boot_are_never_handed_back(cal):
    cal.add(DEVICE, copy(AT + 60))
    cal.add(DEVICE, copy(AT))
    assert cal.lookup(DEVICE, before=AT) is None


def test_only_the_named_device_is_answered(cal):
    cal.add("another-board", copy(AT - 60))
    assert cal.lookup(DEVICE, before=AT) is None


@pytest.mark.parametrize("entry", [
    None, "x", {},
    {"state": "", "accuracy": 3, "saved": AT},
    {"state": "AAEC", "accuracy": 4, "saved": AT},
    {"state": "AAEC", "accuracy": True, "saved": AT},
    {"state": "AAEC", "accuracy": 3, "saved": 0},
    {"state": "AAEC", "accuracy": 3},
])
def test_an_entry_that_is_not_a_usable_copy_is_not_kept(cal, entry):
    assert cal.add(DEVICE, {"bme688": entry}) == 0
    assert cal.count() == 0


def test_the_same_copy_sent_twice_is_kept_once(cal):
    cal.add(DEVICE, copy(AT - 60))
    cal.add(DEVICE, copy(AT - 60))
    assert cal.count() == 1


def test_copies_older_than_keep_days_go_as_new_ones_arrive(cal):
    cal.add(DEVICE, copy(AT - 4 * 86400, state="old"))
    cal.add(DEVICE, copy(AT - 60, state="new"))
    assert cal.count() == 1
    assert cal.lookup(DEVICE, before=AT)["bme688"]["state"] == "new"


def test_the_get_route_answers_with_the_block_the_board_sends(cal, tz):
    client = client_for(cal, tz)
    cal.add(DEVICE, copy(AT - 60))
    rsp = client.get(f"/calibration?device={DEVICE}&before={AT}")
    assert rsp.status_code == 200 and rsp.get_json() == copy(AT - 60)
    assert client.get(f"/calibration?device={DEVICE}&before={AT - 3600}").status_code == 404
    assert client.get(f"/calibration?device={DEVICE}").status_code == 400
    assert client.get(f"/calibration?before={AT}").status_code == 400


def test_a_posted_block_reaches_the_calibration_store(cal, tz):
    client = client_for(cal, tz)
    rsp = client.post("/readings", json={"ts": AT, "device": DEVICE, "co2_ppm": 800,
                                         "calibration": copy(AT - 30)})
    assert rsp.status_code == 204
    assert cal.lookup(DEVICE, before=AT) == copy(AT - 30)


def test_the_readings_store_never_sees_the_block(cal, tmp_path):
    store = ReadingsStore(tmp_path / "readings.db")
    ReadingsIngest(DeviceReports(), store, calibration=cal).accept(
        {"ts": AT, "device": DEVICE, "co2_ppm": 800, "calibration": copy(AT - 30)})
    assert cal.count() == 1
    assert "calibration" not in store.latest()
    store.close()
