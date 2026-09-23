"""config.yaml in the browser: shown as a form and as text, checked as the
server checks it, saved, restarted on."""
import io
import json
import os
import stat

import pytest
from bs4 import BeautifulSoup
from epd_server import ReadingsStore
from flask import Flask

from config_page import config_blueprint
from transfer import Corrupt, Overlap, Transfer
from server import check_config, make_pages
from tests.html import attr, one

GOOD = "server:\n  timezone: Europe/Dublin\nsource:\n  kind: mock\n"
EDITED = "server:\n  timezone: Europe/Dublin\nsource:\n  kind: mock\n  seed: 9\n"
UNKNOWN_PAGE = ("display:\n  pools:\n    co2: [radon.png]\n"
                "  schedule:\n    type: interval\n    every: 600\n")
WITH_DISPLAY = ("server:\n  port: 8080   # the port\n"
                "display:\n  pools:\n    co2: [breathe.png, co2-trace.png]\n"
                "  schedule:\n    type: interval\n    every: 300\n"
                "posts:\n  every: 300\n")


@pytest.fixture
def path(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(GOOD)
    return str(p)


@pytest.fixture
def restarts():
    return []


@pytest.fixture
def client(path, restarts, tz):
    app = Flask(__name__)
    app.register_blueprint(config_blueprint(make_pages(tz, width=1280, height=720), path,
                                            check_config, lambda: restarts.append(1)))
    return app.test_client()


def soup_of(rsp):
    return BeautifulSoup(rsp.get_data(as_text=True), "html.parser")


def posted(soup, form_id="settings-form", **changes) -> dict[str, list[str]]:
    """What the browser posts for the form ``form_id`` as the page shows it,
    with ``changes`` made. A key's dots are double underscores."""
    data: dict[str, list[str]] = {}
    for el in one(soup, f"#{form_id}").select("input[name], select[name], textarea[name]"):
        if el.has_attr("disabled") or el.find_parent("template"):
            continue
        name = attr(el, "name")
        if el.name == "select":
            chosen = el.select_one("option[selected]") or el.select_one("option")
            value = attr(chosen, "value") if chosen else ""
        elif el.name == "textarea":
            value = el.get_text()
        elif attr(el, "type") in ("checkbox", "radio"):
            if not el.has_attr("checked"):
                continue
            value = attr(el, "value")
        else:
            value = attr(el, "value")
        data.setdefault(name, []).append(value)
    for k, v in changes.items():
        data[k.replace("__", ".")] = v if isinstance(v, list) else [v]
    return data


def write(path, text):
    with open(path, "w") as f:
        f.write(text)


def test_the_page_shows_the_file_as_a_form_and_as_text(client, path):
    soup = soup_of(client.get("/web/config"))
    assert one(soup, "textarea[name=text]").get_text() == GOOD
    assert attr(one(soup, ".bar a.config-link"), "aria-current") == "page"
    assert soup.select_one("#read-only") is None
    assert attr(one(soup, "#f-server-timezone"), "value") == "Europe/Dublin"
    port = one(soup, "#f-server-port")
    assert attr(port, "value") == "8080" and not port.has_attr("placeholder")
    assert attr(port, "data-default") == "8080"
    assert one(soup, '[data-field="server.port"] .reset').has_attr("hidden")
    assert soup.select_one('[data-field="source.kind"]') is None
    assert [attr(t, "data-tab") for t in soup.select("nav.tabs a")] == [
        "server", "display", "image", "dock", "storage", "firmware", "mqtt", "yaml"]


def test_the_form_posted_back_as_it_is_changes_nothing(client, path, restarts):
    write(path, WITH_DISPLAY)
    soup = soup_of(client.get("/web/config"))
    rsp = client.post("/web/config", data={**posted(soup), "action": "save"})
    assert one(soup_of(rsp), "#note").get_text() == "Nothing to save."
    assert open(path).read() == WITH_DISPLAY and restarts == []


def test_a_form_save_writes_its_change_keeps_the_rest_and_restarts(client, path, restarts):
    write(path, WITH_DISPLAY)
    soup = soup_of(client.get("/web/config"))
    rsp = client.post("/web/config", data={**posted(soup, server__port="9090", tab="server"),
                                           "action": "save"})
    assert rsp.status_code == 200
    assert open(path).read() == WITH_DISPLAY.replace("port: 8080", "port: 9090")
    assert open(path + ".bak").read() == WITH_DISPLAY
    assert restarts == [1]
    refresh = one(soup_of(rsp), "meta[http-equiv=refresh]")
    assert attr(refresh, "content") == "60; url=config?saved=1#server"


def test_a_value_the_form_cannot_write_is_marked_at_its_field_on_its_tab(client, path, restarts):
    write(path, WITH_DISPLAY)
    soup = soup_of(client.get("/web/config"))
    rsp = client.post("/web/config", data={**posted(soup, server__port="abc"), "action": "save"})
    assert rsp.status_code == 400
    page = soup_of(rsp)
    assert "whole number" in one(page, '[data-field="server.port"] .error').get_text()
    assert attr(one(page, "nav.tabs"), "data-open") == "server"
    assert "problem" in attr(one(page, "#tab-server"), "class")
    assert attr(one(page, "#f-server-port"), "value") == "abc"
    assert attr(one(page, "#f-server-port"), "data-initial") == "8080"
    assert open(path).read() == WITH_DISPLAY and restarts == []


def test_a_problem_the_server_finds_is_shown_at_the_field_it_names(client, path, restarts):
    write(path, WITH_DISPLAY)
    soup = soup_of(client.get("/web/config"))
    rsp = client.post("/web/config", data={**posted(soup, display__pools__pages=["radon.png"]),
                                           "action": "check"})
    assert rsp.status_code == 400
    page = soup_of(rsp)
    assert "radon.png" in one(page, '[data-field="display.pools"] .error').get_text()
    assert attr(one(page, "nav.tabs"), "data-open") == "display"
    assert open(path).read() == WITH_DISPLAY


def test_review_lists_the_changes_and_writes_nothing(client, path, restarts):
    write(path, WITH_DISPLAY)
    soup = soup_of(client.get("/web/config"))
    rsp = client.post("/web/config", data={**posted(soup, server__port="9090"),
                                           "action": "review"})
    assert rsp.get_json() == {"changes": [{"name": "Server · Port", "old": "8080",
                                           "new": "9090"}], "same": False}
    assert open(path).read() == WITH_DISPLAY and restarts == []


def test_a_save_from_config_js_is_answered_in_json(client, path, restarts):
    json = {"Accept": "application/json"}
    rsp = client.post("/web/config", data={"text": EDITED, "action": "save"}, headers=json)
    assert rsp.get_json() == {"saved": True} and restarts == [1]
    rsp = client.post("/web/config", data={"text": EDITED, "action": "save"}, headers=json)
    assert rsp.get_json() == {"saved": False, "same": True} and restarts == [1]
    rsp = client.post("/web/config", data={"text": UNKNOWN_PAGE, "action": "save"}, headers=json)
    assert rsp.status_code == 400 and "radon.png" in rsp.get_json()["problem"]
    assert open(path).read() == EDITED and restarts == [1]


def test_review_of_a_refused_config_says_why(client, path):
    rsp = client.post("/web/config", data={"text": UNKNOWN_PAGE, "action": "review"})
    assert rsp.status_code == 400 and "radon.png" in rsp.get_json()["problem"]


def test_check_says_so_and_changes_nothing(client, path, restarts):
    rsp = client.post("/web/config", data={"text": UNKNOWN_PAGE.replace("radon", "breathe"),
                                           "action": "check"})
    assert rsp.status_code == 200
    assert one(soup_of(rsp), "#note").get_text() == "No problems found."
    notice = one(soup_of(rsp), "dialog#notice")
    assert one(notice, "#notice-title").get_text() == "No problems found"
    assert one(notice, ".lead").get_text() == "Save and restart to apply it."
    assert [b.get_text() for b in notice.select("button")] == ["Close", "Save and restart"]
    assert open(path).read() == GOOD and restarts == []


@pytest.mark.parametrize("text, words", [
    ("server: [", "not YAML"),
    ("- a list", "mapping"),
    (UNKNOWN_PAGE, "radon.png"),
    ("source:\n  kind: bogus\n", "bogus"),
    ("site:\n  altitude_m: [1]\n", ""),
])
def test_a_config_the_server_would_refuse_is_not_saved(client, path, restarts, text, words):
    rsp = client.post("/web/config", data={"text": text, "action": "save"})
    assert rsp.status_code == 400
    problem = one(soup_of(rsp), "#problem").get_text()
    assert problem.startswith("Not saved:") and words in problem
    assert one(soup_of(rsp), "textarea").get_text() == text
    assert open(path).read() == GOOD and restarts == []
    assert not os.path.exists(path + ".bak")


def test_save_keeps_the_old_file_writes_the_new_and_restarts(client, path, restarts):
    text = "source:\r\n  kind: mock\r\n  seed: 9"
    rsp = client.post("/web/config", data={"text": text, "action": "save"})
    assert rsp.status_code == 200
    assert open(path).read() == "source:\n  kind: mock\n  seed: 9\n"
    assert open(path + ".bak").read() == GOOD
    assert restarts == [1]
    assert one(soup_of(rsp), "#restarting") is not None


def test_restore_puts_the_previous_version_back_and_keeps_this_one(client, path, restarts):
    assert soup_of(client.get("/web/config")).select_one("#restore-form") is None
    client.post("/web/config", data={"text": EDITED, "action": "save"})
    assert one(soup_of(client.get("/web/config")), "#restore-form") is not None
    rsp = client.post("/web/config", data={"mode": "restore", "action": "save"})
    assert rsp.status_code == 200
    assert open(path).read() == GOOD and open(path + ".bak").read() == EDITED
    assert restarts == [1, 1]


def test_restore_with_nothing_to_restore_says_so(client, path, restarts):
    rsp = client.post("/web/config", data={"mode": "restore", "action": "save"})
    assert rsp.status_code == 404 and restarts == []


def test_after_a_restart_the_save_bar_says_it_saved(client):
    soup = soup_of(client.get("/web/config?saved=1"))
    assert one(soup, "#settings-form .savebar .status").get_text() == "Saved."
    assert soup.select_one("#note") is None


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes a read-only file anyway")
def test_a_read_only_file_can_be_checked_but_not_saved(client, path, restarts):
    os.chmod(path, stat.S_IRUSR)
    soup = soup_of(client.get("/web/config"))
    assert one(soup, "#read-only") is not None
    assert all(attr(b, "disabled") == "disabled" for b in soup.select("button[value=save]"))
    assert client.post("/web/config", data={"text": EDITED, "action": "check"}).status_code == 200
    assert client.post("/web/config", data={"text": EDITED, "action": "save"}).status_code == 403
    assert restarts == []


def test_an_empty_config_starts_on_the_defaults():
    check_config("")


def test_a_failed_write_says_why_and_does_not_restart(client, path, restarts, monkeypatch):
    def refuse(src, dst):
        raise PermissionError(13, "Permission denied", dst)
    monkeypatch.setattr("config_page.shutil.copyfile", refuse)
    rsp = client.post("/web/config", data={"text": EDITED, "action": "save"})
    assert rsp.status_code == 500
    assert "Permission denied" in one(soup_of(rsp), "#problem").get_text()
    assert restarts == []


def test_a_field_an_environment_variable_sets_is_locked_and_says_so(client, monkeypatch):
    monkeypatch.setenv("SERVER_PORT", "7070")
    soup = soup_of(client.get("/web/config"))
    port = one(soup, "#f-server-port")
    assert attr(port, "disabled") == "disabled" and attr(port, "value") == "7070"
    assert "SERVER_PORT" in one(soup, '[data-field="server.port"] .env').get_text()


def test_text_from_the_file_is_escaped(client, path):
    text = "# </textarea><script>alert(1)</script>\n" + GOOD
    rsp = client.post("/web/config", data={"text": text + "bad: [", "action": "check"})
    soup = soup_of(rsp)
    assert one(soup, "textarea[name=text]").get_text() == text + "bad: ["
    assert [attr(s, "src") for s in soup.find_all("script")] == [
        "rough.iife.min.js", "config.js", "sheet.js", "ago.js"]


def test_a_posted_tab_name_is_one_of_the_tabs(client, path):
    rsp = client.post("/web/config", data={"text": GOOD, "action": "check",
                                           "mode": "form", "tab": '"><b>'})
    assert "<b>" not in attr(one(soup_of(rsp), "input[name=tab]"), "value")


@pytest.fixture
def stores(tmp_path):
    """Two stores on the Storage tab: one with documents, one with none."""
    db = str(tmp_path / "sensor-readings.db")
    store = ReadingsStore(db)
    store.add_many([{"device": "dock", "ts": 1_758_000_000, "co2": 650},
                    {"device": "dock", "ts": 1_758_000_060, "co2": 700}])
    store.close()
    return {"sensor-readings": Transfer("sensor-readings", db),
            "board-reports": Transfer("board-reports", str(tmp_path / "status.db"))}


@pytest.fixture
def exporting(path, restarts, tz, stores):
    app = Flask(__name__)
    app.register_blueprint(config_blueprint(make_pages(tz, width=1280, height=720), path,
                                            check_config, lambda: restarts.append(1), stores))
    return app.test_client()


def test_a_store_with_documents_offers_them_as_a_download(exporting):
    soup = soup_of(exporting.get("/web/config"))
    row = one(soup, '[data-export="sensor-readings"]')
    assert attr(one(row, "a.button"), "href") == "config/export/sensor-readings"
    assert one(row, ".unit").get_text().startswith("≈ ")


def test_a_store_holding_nothing_cannot_be_downloaded(exporting):
    row = one(soup_of(exporting.get("/web/config")), '[data-export="board-reports"]')
    assert not one(row, "a.button").has_attr("href")
    assert one(row, ".unit").get_text() == "No records yet."


def test_the_download_is_every_document_of_that_store(exporting):
    rsp = exporting.get("/web/config/export/sensor-readings")
    lines = rsp.get_data(as_text=True).splitlines()
    assert [json.loads(line)["co2"] for line in lines] == [650, 700]
    assert rsp.mimetype == "application/x-ndjson"
    assert "attachment" in rsp.headers["Content-Disposition"]
    assert "sensor-readings-" in rsp.headers["Content-Disposition"]


def test_a_store_the_page_does_not_offer_is_not_served(exporting):
    assert exporting.get("/web/config/export/config.yaml").status_code == 404


def test_without_stores_the_storage_tab_has_no_export_row(client):
    assert soup_of(client.get("/web/config")).select("[data-export]") == []


def sending(client, store, docs, **form):
    text = "".join(json.dumps(d) + "\n" for d in docs)
    return client.post(f"/web/config/import/{store}", headers={"Accept": "application/json"},
                       content_type="multipart/form-data",
                       data={"file": (io.BytesIO(text.encode()), "readings.jsonl"), **form})


def test_the_import_row_belongs_to_a_form_of_its_own(exporting):
    soup = soup_of(exporting.get("/web/config"))
    row = one(soup, '[data-import="sensor-readings"]')
    assert attr(one(row, "input[type=file]"), "form") == "import-sensor-readings"
    assert one(soup, "#import-sensor-readings").find_parent(id="settings-form") is None


def test_a_file_of_new_records_goes_in_and_says_how_many(exporting):
    rsp = sending(exporting, "sensor-readings", [{"device": "dock", "ts": 1_758_000_600, "co2": 800}])
    assert rsp.status_code == 200
    assert rsp.json["words"] == "Added 1 of 1 records."
    assert rsp.json["shown"].startswith("≈ ")


def test_records_the_store_holds_stop_the_import_and_say_so(exporting):
    rsp = sending(exporting, "sensor-readings", [{"device": "dock", "ts": 1_758_000_000, "co2": 1}])
    assert rsp.status_code == 409
    assert (rsp.json["held"], rsp.json["total"]) == (1, 1)
    assert "1 of 1 records already exist" in rsp.json["words"]


def test_replace_puts_the_file_over_the_records_that_exist(exporting):
    rsp = sending(exporting, "sensor-readings", [{"device": "dock", "ts": 1_758_000_000, "co2": 1}],
                  replace="true")
    assert rsp.status_code == 200
    assert rsp.json["words"] == "Added 0 of 1 records. 1 replaced."


def test_a_corrupted_file_is_refused(exporting):
    rsp = exporting.post("/web/config/import/sensor-readings",
                         headers={"Accept": "application/json"},
                         content_type="multipart/form-data",
                         data={"file": (io.BytesIO(b"{ not json\n"), "readings.jsonl")})
    assert rsp.status_code == 400
    assert "corrupted and cannot be imported" in rsp.json["words"]


def test_a_store_the_page_does_not_offer_takes_no_file(exporting):
    assert sending(exporting, "config.yaml", [{"device": "d", "ts": 1}]).status_code == 404


def test_without_a_file_it_says_to_choose_one(exporting):
    rsp = exporting.post("/web/config/import/sensor-readings",
                         headers={"Accept": "application/json"},
                         content_type="multipart/form-data", data={})
    assert rsp.status_code == 400 and rsp.json["words"] == "Choose a file to import."


def test_a_page_that_cannot_ask_gets_the_answer_under_the_row(exporting):
    text = json.dumps({"device": "dock", "ts": 1_758_000_600, "co2": 800}) + "\n"
    rsp = exporting.post("/web/config/import/sensor-readings",
                         content_type="multipart/form-data",
                         data={"file": (io.BytesIO(text.encode()), "readings.jsonl")})
    row = one(soup_of(rsp), '[data-import="sensor-readings"]')
    assert one(row, "p").get_text() == "Added 1 of 1 records."


# ── The Dock tab ────────────────────────────────────────────────────

@pytest.fixture
def dock_report():
    return {}


@pytest.fixture
def dock_offline():
    return False


@pytest.fixture
def dock(tmp_path, dock_report, dock_offline):
    from dock_settings import BoardSettings, DockSettings
    from schedule import PostSchedule
    from sources.calibration import CalibrationStore
    from tests.conftest import AT, TZ
    store = CalibrationStore(tmp_path / "calibration.db")
    yield BoardSettings(DockSettings(), PostSchedule(300, TZ), store,
                        lambda device: ({"doc": dock_report, "age_s": 3600,
                                         "offline": dock_offline} if dock_report else None),
                        now=lambda: AT)
    store.close()


@pytest.fixture
def dock_client(path, restarts, tz, dock):
    app = Flask(__name__)
    app.register_blueprint(config_blueprint(make_pages(tz, width=1280, height=720), path,
                                            check_config, lambda: restarts.append(1), dock=dock))
    return app.test_client()


def test_the_dock_tab_holds_the_dock_block_and_a_recalibration(dock_client):
    soup = soup_of(dock_client.get("/web/config"))
    panel = one(soup, "#panel-dock")

    assert attr(one(panel, '[data-field="dock.pm.warmup_s"] input'), "value") == "35"
    assert " ".join(one(panel, "#dock-applied").get_text().split()) == \
        "No report from the dock yet. Settings apply once it connects."
    sections = panel.select(".section")
    assert len(sections) == 7 and all(sec.select_one("h2.group") for sec in sections)
    heading = one(panel, '.section:has([data-field="dock.scd41.self_calibration"]) h2')
    assert [span.get_text() for span in heading.select("span")] == ["CO₂", "SCD41"]
    assert attr(one(panel, "#recalibrate-ppm"), "form") == "recalibrate-form"
    group = one(panel, "[data-recalibrate]").find_parent(class_="fields")
    assert group.select_one('[data-field="dock.scd41.self_calibration"]') is not None
    assert one(soup, "#recalibrate-form").find_parent(id="settings-form") is None


def test_a_setting_changed_on_the_dock_tab_is_saved_under_dock(dock_client, path, restarts):
    soup = soup_of(dock_client.get("/web/config"))

    rsp = dock_client.post("/web/config", data={
        **posted(soup, dock__led__brightness_pct="40"), "action": "save"})

    assert rsp.status_code == 200
    assert "brightness_pct: 40" in open(path).read()
    assert restarts == [1]


def test_recalibrate_asks_the_dock_and_does_not_restart(dock_client, dock, path, restarts):
    before = open(path).read()

    rsp = dock_client.post("/web/config", data={"mode": "recalibrate", "ppm": "420"})

    assert rsp.status_code == 303
    assert rsp.headers["Location"].endswith("config#dock")
    assert dock.pending()["ppm"] == 420
    assert open(path).read() == before
    assert restarts == []
    words = one(soup_of(dock_client.get("/web/config")), "#recalibrate-state").get_text()
    assert words.startswith("Waiting for the dock's next report: 420 ppm, asked ")


def test_a_reference_out_of_range_is_refused_on_the_dock_tab(dock_client, dock):
    rsp = dock_client.post("/web/config", data={"mode": "recalibrate", "ppm": "50"})
    soup = soup_of(rsp)

    assert rsp.status_code == 400
    assert attr(one(soup, "nav.tabs"), "data-open") == "dock"
    assert one(soup, '[data-recalibrate] .error').get_text() == "Enter a value from 400 to 2000 ppm."
    assert attr(one(soup, "#recalibrate-ppm"), "value") == "50"
    assert dock.pending() is None


@pytest.mark.parametrize("dock_report, words", [
    ({"client": {"settings": {"version": "00000000"}}},
     "The dock takes these settings before its next report, at 21:50."),
    ({"client": {"recalibrated": {"id": 1_758_600_000, "ppm": 420, "ok": True,
                                  "correction_ppm": -12}}},
     "Corrected by -12 ppm."),
    ({"client": {"recalibrated": {"id": 1_758_600_000, "ppm": 420, "ok": False}}},
     "The SCD41 refused it."),
])
def test_the_dock_tab_says_what_the_dock_reported(dock_client, words):
    text = one(soup_of(dock_client.get("/web/config")), "#panel-dock").get_text()

    assert words in text


def test_a_key_the_dock_refused_is_named_as_the_form_names_it(dock_client, dock_report, dock):
    dock_report["client"] = {"settings": {"version": dock.settings.version,
                                          "refused": ["pm.warmup_s"]}}

    soup = soup_of(dock_client.get("/web/config"))

    assert one(soup, "#dock-refused").get_text() == \
        "Refused by the dock: Fan warm-up. Check the dock's firmware version."


def test_the_bsec_rate_is_saved_as_a_number(dock_client, path):
    soup = soup_of(dock_client.get("/web/config"))
    assert one(soup, '[data-field="dock.bsec.sample_s"] input[checked]')["value"] == "300"

    dock_client.post("/web/config", data={**posted(soup, dock__bsec__sample_s="3"), "action": "save"})

    assert "sample_s: 3\n" in open(path).read()
    check_config(open(path).read())



@pytest.mark.parametrize("dock_report", [{"client": {"settings": {"version": "00000000"}}}])
@pytest.mark.parametrize("dock_offline", [True])
def test_an_offline_dock_greys_out_its_tab(dock_client, path):
    panel = one(soup_of(dock_client.get("/web/config")), "#panel-dock")

    assert one(panel, "#dock-offline").get_text() == "Offline"
    assert "Last report 1 h ago." in panel.get_text()
    for el in panel.select('[data-field^="dock."] input'):
        assert el.has_attr("disabled"), el
    assert one(panel, "#recalibrate-ppm").has_attr("disabled")
    assert one(panel, "[data-recalibrate] button").has_attr("disabled")
    assert not panel.select('[data-field^="dock."] .reset')


@pytest.mark.parametrize("dock_report", [{"client": {"settings": {"version": "00000000"}}}])
@pytest.mark.parametrize("dock_offline", [True])
def test_the_dock_lines_come_fresh_for_config_js(dock_client):
    live = dock_client.get("/web/config/live").get_json()
    state = BeautifulSoup(live["state"], "html.parser")

    assert live["offline"] is True
    assert attr(one(state, "#dock-state"), "data-offline") == "true"
    assert one(state, "#dock-offline").get_text() == "Offline"
    assert attr(one(state, "#dock-applied [data-age]"), "data-age") == "3600"
    assert live["recalibration"].startswith("Keep the dock in air of a known CO₂ level")


def test_the_page_starts_with_the_dock_lines_config_js_replaces(dock_client):
    soup = soup_of(dock_client.get("/web/config"))

    assert attr(one(soup, "#panel-dock #dock-state"), "data-offline") == "false"


def test_without_a_dock_there_are_no_live_lines(client):
    assert client.get("/web/config/live").status_code == 404


def test_a_greyed_out_field_keeps_its_value_when_another_tab_saves(dock_client, path):
    """A disabled input is not posted, and a field the form leaves out stays."""
    with open(path, "a") as f:
        f.write("dock:\n  led:\n    brightness_pct: 40\n")
    soup = soup_of(dock_client.get("/web/config"))
    data = {k: v for k, v in posted(soup, source__seed="9").items() if not k.startswith("dock.")}

    dock_client.post("/web/config", data={**data, "action": "save"})

    assert "brightness_pct: 40" in open(path).read()


@pytest.mark.parametrize("dock_report", [{"client": {"settings": {"version": "00000000"}}}])
def test_a_dock_that_reports_can_be_changed(dock_client):
    panel = one(soup_of(dock_client.get("/web/config")), "#panel-dock")

    assert panel.select_one("#dock-offline") is None
    assert not one(panel, '[data-field="dock.pm.warmup_s"] input').has_attr("disabled")
    assert not one(panel, "#recalibrate-ppm").has_attr("disabled")
    assert one(panel, "#dock-waiting").get_text() == "Not synchronized"
    assert " ".join(one(panel, "#dock-applied").get_text().split()) == \
        "Not synchronized The dock takes these settings before its next report, at 21:50."


def test_the_quiet_hours_settings_share_a_box_that_shows_with_them(dock_client):
    panel = one(soup_of(dock_client.get("/web/config")), "#panel-dock")
    box = one(panel, ".subsection")

    assert attr(box, "data-when") == "posts.quiet=true"
    assert [attr(f, "data-field") for f in box.select("[data-field]")] == [
        "posts.quiet.from", "posts.quiet.to", "posts.quiet.every"]
    assert one(box, '[data-field="posts.quiet.every"] .name').get_text() == "Report every"


def test_a_report_interval_set_by_the_environment_shows_in_minutes(dock_client, monkeypatch):
    monkeypatch.setenv("POSTS_EVERY", "600")
    field = one(soup_of(dock_client.get("/web/config")), '[data-field="posts.every"] input')

    assert attr(field, "value") == "10" and field.has_attr("disabled")


def test_a_dock_on_the_saved_settings_is_synchronized(dock_client, dock_report, dock):
    dock_report["client"] = {"settings": {"version": dock.settings.version, "refused": []}}

    soup = soup_of(dock_client.get("/web/config"))

    assert one(soup, "#dock-synced").get_text() == "Synchronized"
    assert " ".join(one(soup, "#dock-applied").get_text().split()) == \
        "Synchronized Last report 1 h ago."


# ── The Image tab ───────────────────────────────────────────────────

def image_client(path, tz, head):
    app = Flask(__name__)
    app.register_blueprint(config_blueprint(
        make_pages(tz, width=1280, height=720), path, check_config, lambda: None,
        boards=lambda device: {"doc": {"client": head}} if device == "canary-head" else None))
    return app.test_client()


def test_the_position_grid_stands_for_both_alignments(client):
    panel = one(soup_of(client.get("/web/config")), "#panel-image")
    grid = one(panel, ".grid3")

    assert (attr(grid, "data-x"), attr(grid, "data-y")) == ("image.innerAlignX", "image.innerAlignY")
    assert len(grid.select("button")) == 9
    assert [attr(b, "aria-label") for b in grid.select('[aria-pressed="true"]')] == ["Centre"]
    assert attr(grid.select("button")[0], "aria-label") == "Top left"
    for key in ("image.innerAlignX", "image.innerAlignY"):
        assert "by-position" in one(panel, f'[data-field="{key}"]')["class"]


@pytest.mark.parametrize("head, words, klass", [
    ({"board": "Inkplate5V2", "width": 1280, "height": 720},
     "The head reports 1280 × 720 px, Inkplate5V2.", "help"),
    ({"board": "Inkplate10", "width": 1200, "height": 825},
     "Not the head's size: it reports 1200 × 825 px, Inkplate10. Set Width and Height to match.",
     "error"),
])
def test_the_size_line_says_what_the_head_reports(path, tz, head, words, klass):
    line = one(soup_of(image_client(path, tz, head).get("/web/config")), "#head-size")

    assert line.get_text() == words and klass in line["class"]


def test_no_size_line_before_the_head_reports(path, tz):
    soup = soup_of(image_client(path, tz, {"board": "Inkplate5V2"}).get("/web/config"))

    assert soup.select_one("#head-size") is None



def test_a_recalibration_says_when_it_expires(dock_client, dock):
    dock_client.post("/web/config", data={"mode": "recalibrate", "ppm": "420"})

    from datetime import datetime
    from tests.conftest import AT
    words = one(soup_of(dock_client.get("/web/config")), "#recalibrate-state").get_text()

    # In the process's own zone, which the server sets to server.timezone.
    assert words.endswith(f"Expires at {datetime.fromtimestamp(AT + 3600):%H:%M}.")


def test_a_recalibration_the_dock_never_ran_says_it_expired(dock_client, dock):
    from tests.conftest import AT
    dock.requests.request("canary-dock", "scd41", 450, AT - 2 * 3600)

    words = one(soup_of(dock_client.get("/web/config")), "#recalibrate-state").get_text()

    assert words == "Recalibration to 450 ppm expired: no report from the dock within an hour."


def test_before_any_recalibration_the_row_says_how_to_do_one(dock_client):
    words = one(soup_of(dock_client.get("/web/config")), "#recalibrate-state").get_text()

    assert words.startswith("Keep the dock in air of a known CO₂ level for 3 minutes")
