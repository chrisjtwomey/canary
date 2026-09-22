"""What a store holds, as a file to download: one JSON document a line."""
import json
import os

import pytest
from epd_server import ReadingsStore

from transfer import Corrupt, Overlap, Transfer
from sources.calibration import CalibrationStore

AT = 1_758_000_000


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "sensor-readings.db")


@pytest.fixture
def readings(db):
    store = ReadingsStore(db)
    store.add_many([{"device": "dock", "ts": AT + 60, "co2": 700},
                    {"device": "dock", "ts": AT, "co2": 650},
                    {"device": "head", "ts": AT + 30, "client": {"ip": "10.0.0.9"}}])
    store.close()
    return Transfer("sensor-readings", db)


def docs(export):
    return [json.loads(line) for line in export.lines()]


def test_every_document_is_a_line_of_its_own(readings):
    lines = list(readings.lines())
    assert len(lines) == 3
    assert all(line.endswith("\n") for line in lines)


def test_the_documents_come_back_oldest_first(readings):
    assert [d["ts"] for d in docs(readings)] == [AT, AT + 30, AT + 60]


def test_a_document_keeps_everything_the_board_sent(readings):
    assert docs(readings)[2] == {"device": "dock", "ts": AT + 60, "co2": 700}


def test_the_size_is_what_the_download_weighs(readings):
    exact = sum(len(line.encode()) for line in readings.lines())
    assert readings.size() == exact


def test_the_size_of_a_big_store_is_taken_from_a_sample(tmp_path, monkeypatch):
    monkeypatch.setattr("transfer.SAMPLE_ROWS", 10)
    path = str(tmp_path / "big.db")
    store = ReadingsStore(path)
    store.add_many([{"device": "dock", "ts": AT + i, "co2": 700} for i in range(200)])
    store.close()
    export = Transfer("sensor-readings", path)
    exact = sum(len(line.encode()) for line in export.lines())
    assert abs(export.size() - exact) < exact * 0.02


def test_a_store_that_does_not_exist_yet_holds_nothing(tmp_path):
    export = Transfer("sensor-readings", str(tmp_path / "none.db"))
    assert export.size() == 0
    assert list(export.lines()) == []


def test_reading_a_store_does_not_create_the_file(tmp_path):
    path = str(tmp_path / "none.db")
    Transfer("sensor-readings", path).size()
    assert not os.path.exists(path)


def test_a_store_with_no_documents_has_no_size(tmp_path):
    path = str(tmp_path / "empty.db")
    ReadingsStore(path).close()
    assert Transfer("sensor-readings", path).size() == 0


def test_a_calibration_copy_comes_back_with_its_columns(tmp_path):
    path = str(tmp_path / "calibration.db")
    store = CalibrationStore(path, keep_days=0, now=lambda: float(AT))
    store.add("dock", {"bme688": {"state": "QUJD", "accuracy": 3, "saved": AT}})
    assert docs(Transfer("calibration", path, "calibration")) == [
        {"device": "dock", "sensor": "bme688", "saved": AT, "accuracy": 3, "state": "QUJD"}]


def test_the_documents_go_back_into_a_store_unchanged(readings, tmp_path):
    """An export is what a store takes, so putting one back adds what is
    missing and changes nothing else."""
    other = ReadingsStore(str(tmp_path / "copy.db"))
    assert other.add_many(docs(readings)) == [True, True, True]
    assert other.add_many(docs(readings)) == [False, False, False]
    assert other.count() == 3


def took(export, lines, overwrite=False):
    return export.take([line if isinstance(line, str) else json.dumps(line) + "\n"
                        for line in lines], overwrite)


def test_a_file_of_new_documents_goes_in(readings, db):
    fresh = [{"device": "dock", "ts": AT + 600, "co2": 800}]
    assert took(readings, fresh) == {"added": 1, "held": 0, "total": 1}
    assert ReadingsStore(db).count() == 4


def test_a_file_the_store_already_holds_is_refused(readings, db):
    held = [{"device": "dock", "ts": AT, "co2": 650},
            {"device": "dock", "ts": AT + 600, "co2": 800}]
    with pytest.raises(Overlap) as caught:
        took(readings, held)
    assert (caught.value.held, caught.value.total) == (1, 2)
    assert ReadingsStore(db).count() == 3, "nothing is written until it is told to"


def test_overwrite_puts_the_file_over_what_is_held(readings, db):
    both = [{"device": "dock", "ts": AT, "co2": 111},
            {"device": "dock", "ts": AT + 600, "co2": 800}]
    assert took(readings, both, overwrite=True) == {"added": 1, "held": 1, "total": 2}
    kept = {d["ts"]: d.get("co2") for d in docs(readings)}
    assert kept[AT] == 111 and kept[AT + 600] == 800


def test_a_corrupted_file_is_refused_whole(readings, db):
    with pytest.raises(Corrupt) as caught:
        took(readings, [{"device": "dock", "ts": AT + 600, "co2": 800},
                        "{not json\n",
                        {"device": "dock", "ts": AT + 900, "co2": 810}])
    assert caught.value.line == 2
    assert ReadingsStore(db).count() == 3


def test_a_document_without_a_time_is_corrupt(readings, db):
    with pytest.raises(Corrupt) as caught:
        took(readings, [{"device": "dock", "co2": 800}])
    assert caught.value.line == 1 and "ts" in caught.value.why


def test_blank_lines_are_not_documents(readings, db):
    assert took(readings, ["\n", {"device": "dock", "ts": AT + 600, "co2": 800}, "\n"]) == \
        {"added": 1, "held": 0, "total": 1}


def test_a_file_bigger_than_one_batch_goes_in_whole(readings, db, monkeypatch):
    monkeypatch.setattr("transfer.ROWS_AT_A_TIME", 10)
    many = [{"device": "head", "ts": AT + 1000 + i, "co2": 700} for i in range(25)]
    assert took(readings, many) == {"added": 25, "held": 0, "total": 25}
    assert ReadingsStore(db).count() == 28


def test_a_store_that_is_not_kept_cannot_take_a_file(tmp_path):
    export = Transfer("sensor-readings", str(tmp_path / "none.db"))
    with pytest.raises(FileNotFoundError):
        took(export, [{"device": "dock", "ts": AT, "co2": 650}])


def test_a_calibration_file_goes_back_in(tmp_path):
    path = str(tmp_path / "calibration.db")
    store = CalibrationStore(path, keep_days=0, now=lambda: float(AT))
    store.add("dock", {"bme688": {"state": "QUJD", "accuracy": 3, "saved": AT}})
    export = Transfer("calibration", path, "calibration")
    copy = {"device": "dock", "sensor": "bme688", "saved": AT + 60, "accuracy": 2, "state": "RUZH"}
    assert took(export, [copy]) == {"added": 1, "held": 0, "total": 1}
    assert copy in docs(export)


def test_a_line_that_is_not_a_calibration_copy_is_corrupt(tmp_path):
    path = str(tmp_path / "calibration.db")
    CalibrationStore(path, keep_days=0).add("dock", {})
    export = Transfer("calibration", path, "calibration")
    with pytest.raises(Corrupt):
        took(export, [{"device": "dock", "sensor": "bme688", "saved": AT,
                       "accuracy": 9, "state": "QUJD"}])
