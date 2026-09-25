"""The config form: what a filled-in form writes into config.yaml, and what it leaves."""
import dataclasses
import os

import pytest
import yaml
from werkzeug.datastructures import MultiDict

import config_form as cf
from schedule import DEFAULT_PAGE_RANGES
from server import check_config, load_settings

EXAMPLE = open(os.path.join(os.path.dirname(__file__), "..", "config.example.yaml")).read()


def as_posted(text: str, **changes) -> MultiDict:
    """The form as the page posts it for ``text``, with ``changes`` made.
    A key's dots are double underscores; a list value posts each item."""
    shown = cf.shown(cf.read(text))
    form = MultiDict()
    for f in cf.FIELDS:
        v = shown[f.key]
        if f.kind == "pools":
            form.add(f.key, "1")
            for name, pages in v:
                form.add(f.key + ".name", name)
                form.add(f.key + ".pages", pages)
        elif f.kind == "times":
            form.add(f.key, "1")
            for at, pool in v:
                form.add(f.key + ".at", at)
                form.add(f.key + ".pool", pool)
        elif f.kind == "clock":
            form.add(f.key, "1")
            for start, every in v:
                form.add(f.key + ".from", start)
                form.add(f.key + ".every", every)
        elif f.kind == "looks":
            form.add(f.key, "1")
            for trigger, pattern, interval in v:
                form.add(f.key + ".trigger", trigger)
                form.add(f.key + ".pattern", pattern)
                form.add(f.key + ".length_s", interval)
        else:
            form.add(f.key, v)
    for k, v in changes.items():
        form.setlist(k.replace("__", "."), v if isinstance(v, list) else [v])
    return form


def edit(text: str = EXAMPLE, **changes) -> cf.Edit:
    e = cf.apply(text, as_posted(text, **changes))
    assert e.errors == {}
    return e


def removed_and_added(old: str, new: str) -> tuple[list[str], list[str]]:
    a, b = old.splitlines(), new.splitlines()
    return [ln for ln in a if ln not in b], [ln for ln in b if ln not in a]


def test_ruamel_writes_the_example_back_as_it_was():
    assert cf.Doc(EXAMPLE).text() == EXAMPLE


def test_an_unchanged_form_changes_nothing():
    e = edit()
    assert e.text == EXAMPLE and e.changed == []


def test_a_new_value_changes_its_line_and_keeps_its_comment():
    e = edit(site__altitude_m="12")
    assert removed_and_added(EXAMPLE, e.text) == (
        ["  altitude_m: 10    # pressure is reduced to sea level, as forecasts quote it"],
        ["  altitude_m: 12    # pressure is reduced to sea level, as forecasts quote it"])
    assert e.changed == ["site.altitude_m"]


def test_an_empty_field_takes_its_key_out_and_the_lines_after_it_stay():
    e = edit(server__regen_lead_seconds="")
    assert removed_and_added(EXAMPLE, e.text) == (
        ["  regen_lead_seconds: 60"], [])
    assert "\n\n# What the client shows, and when." in e.text


def test_a_new_key_goes_after_its_blocks_comments_and_before_the_blank_line():
    e = edit(source__path="data/sensor-readings.db")
    lines = e.text.splitlines()
    i = lines.index("  path: data/sensor-readings.db")
    assert lines[i - 1].startswith("  # keep_days: 0")
    assert lines[i + 1] == "" and lines[i + 2].startswith("status:")


def test_a_block_left_empty_goes_without_doubling_the_blank_line():
    e = edit(status__keep_days="")
    assert "status:" not in e.text
    assert "\n\n\n" not in e.text
    assert "status" not in cf.read(e.text)


def test_a_new_block_goes_at_the_end_after_a_blank_line():
    text = "server:\n  port: 8080\n"
    e = cf.apply(text, MultiDict({"site.altitude_m": "12"}))
    assert e.text == "server:\n  port: 8080\n\nsite:\n  altitude_m: 12\n"


def test_the_files_indentation_is_kept():
    text = "server:\n    port: 8080   # the port\n    timezone: Europe/Dublin\n"
    e = cf.apply(text, MultiDict({"server.port": "9090"}))
    assert e.text == "server:\n    port: 9090   # the port\n    timezone: Europe/Dublin\n"


@pytest.mark.parametrize("value", ["yes", "on", "null", "12", "a: b", "#x", " padded"])
def test_a_string_pyyaml_would_misread_is_quoted(value):
    e = cf.apply(EXAMPLE, MultiDict({"mqtt.prefix": value}))
    assert cf.read(e.text)["mqtt"]["prefix"] == value.strip()


def test_the_lights_schedule_turned_on_writes_the_defaults_quoted():
    e = edit(dock__led__schedule="true")
    assert ('    schedule:       # the hours the light is on, as {from: "07:00", to: "01:00"}; '
            '{} for all day\n      from: "07:00"\n      to: "01:00"\n') in e.text
    assert cf.read(e.text)["dock"]["led"]["schedule"] == {"from": "07:00", "to": "01:00"}


def test_the_lights_schedule_turned_off_is_an_empty_block_again():
    on = edit(dock__led__schedule="true", dock__led__schedule__to="23:30").text
    assert cf.read(on)["dock"]["led"]["schedule"] == {"from": "07:00", "to": "23:30"}
    e = edit(on, dock__led__schedule="false")
    assert cf.read(e.text)["dock"]["led"]["schedule"] == {}


def test_the_lights_schedule_left_off_changes_nothing():
    e = edit(dock__led__schedule="false")
    assert e.text == EXAMPLE and e.changed == []


def test_the_sync_schedule_is_shown_in_minutes_from_the_earliest_start():
    assert cf.shown(cf.read(EXAMPLE))["dock.sync"] == [("01:00", "30"), ("07:00", "5")]


def test_a_split_schedule_is_written_one_range_to_a_line_in_seconds():
    e = edit(dock__sync__from=["01:00", "07:00", "22:00"], dock__sync__every=["30", "10", "0"])
    assert ('  sync:             # when it takes a reading and syncs, in server.timezone: '
            'each range runs until\n') in e.text
    assert ('    - {from: "01:00", every: 1800}\n    - {from: "07:00", every: 600}\n'
            '    - {from: "22:00", every: 0}\n') in e.text
    assert cf.read(e.text)["dock"]["sync"] == [{"from": "01:00", "every": 1800},
                                               {"from": "07:00", "every": 600},
                                               {"from": "22:00", "every": 0}]
    assert e.changed == ["dock.sync"]


def test_ranges_in_any_order_are_written_from_the_earliest_start():
    e = edit(dock__sync__from=["22:00", "07:00"], dock__sync__every=["0", "5"])
    assert cf.read(e.text)["dock"]["sync"] == [{"from": "07:00", "every": 300},
                                               {"from": "22:00", "every": 0}]


def test_a_schedule_without_a_block_is_written_where_the_dock_block_is():
    text = EXAMPLE.replace('  sync:             # when it takes a reading and syncs, in '
                           'server.timezone: each range runs until\n'
                           '                    # the next starts, slots on the wall clock '
                           '(:00, :05 ...); every: 0 is off\n'
                           '    - {from: "01:00", every: 1800}\n    - {from: "07:00", every: 300}\n',
                           "")
    assert "sync" not in cf.read(text)["dock"]
    assert edit(text).changed == []
    e = edit(text, dock__sync__from=["00:00"], dock__sync__every=["10"])
    assert cf.read(e.text)["dock"]["sync"] == [{"from": "00:00", "every": 600}]


@pytest.mark.parametrize("starts, everies, words", [
    (["07:00", "25:00"], ["5", "5"], "25:00: not a time."),
    (["07:00"], ["1.5"], "From 07:00: enter a whole number of minutes."),
    (["07:00"], ["-5"], "From 07:00: enter 0 to 1440 minutes."),
    (["07:00", "7:00"], ["5", "10"], "Two time ranges start at 07:00."),
    ([], [], "Keep at least one time range."),
    ([f"{h:02d}:00" for h in range(9)], ["5"] * 9, "At most 8 time ranges."),
])
def test_a_schedule_the_form_cannot_write_is_refused_at_its_field(starts, everies, words):
    e = cf.apply(EXAMPLE, as_posted(EXAMPLE, dock__sync__from=starts, dock__sync__every=everies))
    assert e.errors == {"dock.sync": words} and e.text == EXAMPLE


LOOKS_LINES = ('    looks:\n'
               '      - {trigger: starting, pattern: pulse, length_s: 0.5}\n'
               '      - {trigger: no_wifi, pattern: flash, length_s: 1}\n'
               '      - {trigger: post_failed, pattern: flash, length_s: 2}\n'
               '      - {trigger: sensor_missing, pattern: flash, length_s: 3}\n'
               '      - {trigger: well, pattern: pulse, length_s: 1}\n')


def looks(text=EXAMPLE, *rows):
    """An edit of the light's looks to ``rows`` of (trigger, pattern, interval)."""
    return cf.apply(text, as_posted(text, **{
        "dock__led__looks__trigger": [r[0] for r in rows],
        "dock__led__looks__pattern": [r[1] for r in rows],
        "dock__led__looks__length_s": [r[2] for r in rows]}))


def test_the_lights_looks_are_a_row_for_each_trigger_in_their_order():
    assert cf.shown(cf.read(EXAMPLE))["dock.led.looks"] == [
        ("starting", "pulse", "0.5"), ("no_wifi", "flash", "1"), ("post_failed", "flash", "2"),
        ("sensor_missing", "flash", "3"), ("well", "pulse", "1")]


def test_a_double_or_a_triple_is_written_by_its_name():
    e = looks(EXAMPLE, ("post_failed", "triple_flash", "1.9"), ("well", "double_pulse", "0.9"))
    assert ('      - {trigger: post_failed, pattern: triple_flash, length_s: 1.9}\n'
            '      - {trigger: well, pattern: double_pulse, length_s: 0.9}\n') in e.text
    check_config(e.text)


def test_looks_are_written_one_to_a_line_in_the_triggers_order():
    e = looks(EXAMPLE, ("well", "solid", "1"), ("no_wifi", "flash", "0.25"))
    assert ('    looks:\n      - {trigger: no_wifi, pattern: flash, length_s: 0.25}\n'
            '      - {trigger: well, pattern: solid}\n') in e.text
    assert e.errors == {} and e.changed == ["dock.led.looks"]
    check_config(e.text)


def test_no_looks_are_written_as_none():
    e = looks(EXAMPLE)
    assert "    looks: []\n" in e.text and e.changed == ["dock.led.looks"]
    check_config(e.text)


def test_the_interval_of_a_look_that_does_not_repeat_is_not_compared():
    text = EXAMPLE.replace("{trigger: well, pattern: pulse, length_s: 1}",
                           "{trigger: well, pattern: solid, length_s: 4}")
    e = edit(text)
    assert e.text == text and e.changed == []
    e = looks(text, ("well", "off", "not a number"))
    assert e.errors == {} and '      - {trigger: well, pattern: "off"}\n' in e.text
    check_config(e.text)


def test_looks_without_a_block_are_written_where_the_led_block_is():
    text = EXAMPLE.replace(LOOKS_LINES, "")
    assert "looks" not in cf.read(text)["dock"]["led"]
    assert edit(text).changed == []
    e = looks(text, ("well", "pulse", "2"))
    assert cf.read(e.text)["dock"]["led"]["looks"] == [
        {"trigger": "well", "pattern": "pulse", "length_s": 2}]


@pytest.mark.parametrize("rows, words", [
    ((("", "pulse", "1"),), "Choose a trigger for each row."),
    ((("well", "pulse", "1"), ("well", "off", "1")), "Two rows for Well."),
    ((("no_wifi", "blink", "1"),), "No Wi-Fi: choose a pattern."),
    ((("no_wifi", "flash", ""),), "No Wi-Fi: enter a length in seconds."),
    ((("no_wifi", "flash", "0.2"),), "No Wi-Fi: enter 0.25 to 10 seconds for a flash."),
    ((("no_wifi", "pulse", "11"),), "No Wi-Fi: enter 0.25 to 10 seconds for a pulse."),
    ((("no_wifi", "triple_flash", "1.1"),),
     "No Wi-Fi: enter 1.2 to 10 seconds for a triple flash."),
])
def test_looks_the_form_cannot_write_are_refused_at_their_field(rows, words):
    e = looks(EXAMPLE, *rows)
    assert e.errors == {"dock.led.looks": words} and e.text == EXAMPLE


def test_pools_change_come_and_go_and_keep_their_order():
    e = edit(display__pools__name=["comfort", "co2", "extra"],
             display__pools__pages=["comfort.png", "breathe.png, co2-trace.png", "day.png"])
    assert cf.read(e.text)["display"]["pools"] == {
        "comfort": ["comfort.png"], "co2": ["breathe.png", "co2-trace.png"], "extra": ["day.png"]}
    assert list(cf.read(e.text)["display"]["pools"]) == ["comfort", "co2", "extra"]
    assert "    co2: [breathe.png, co2-trace.png]" in e.text
    assert "  schedule:\n    type: timeranges" in e.text


def test_the_page_schedule_is_shown_in_minutes_from_the_earliest_start():
    assert cf.shown(cf.read(EXAMPLE))["display.schedule.ranges"] == [("00:00", "5")]


def test_a_split_page_schedule_is_written_under_the_schedule_one_range_to_a_line():
    e = edit(display__schedule__ranges__from=["00:00", "07:00", "23:00"],
             display__schedule__ranges__every=["60", "5", "0"])
    assert ('      - {from: "00:00", every: 3600}\n      - {from: "07:00", every: 300}\n'
            '      - {from: "23:00", every: 0}\n    reshuffle_hours: 3\n') in e.text
    assert e.changed == ["display.schedule.ranges"]
    check_config(e.text)


def test_the_heads_sync_is_shown_in_minutes_and_written_in_seconds():
    assert cf.shown(cf.read(EXAMPLE))["head.sync.every"] == "30"
    e = edit(head__sync__every="10")
    assert "    every: 600      # seconds" in e.text and e.changed == ["head.sync.every"]
    check_config(e.text)


def test_a_field_an_environment_variable_sets_is_left_alone(monkeypatch):
    monkeypatch.setenv("SERVER_PORT", "7070")
    e = cf.apply(EXAMPLE, MultiDict({"server.port": "1234"}))
    assert e.text == EXAMPLE and e.changed == []


@pytest.mark.parametrize("key, value, words", [
    ("server.port", "abc", "whole number"),
    ("server.port", "70000", "at most 65535"),
    ("dock.led.schedule.from", "25:00", "HH:MM"),
    ("image.innerAlignX", "middle", "one of"),
])
def test_a_value_the_form_cannot_write_is_refused_at_its_field(key, value, words):
    e = cf.apply(EXAMPLE, MultiDict({key: value}))
    assert words in e.errors[key] and e.text == EXAMPLE


@pytest.mark.parametrize("names, pages, words", [
    (["", "x"], ["a.png", ""], "needs a name"),
    (["co2", "co2"], ["a.png", "b.png"], "Duplicate pool"),
    (["co2"], [""], "no images"),
    ([], [], "at least one pool"),
])
def test_pools_the_form_cannot_write_are_refused(names, pages, words):
    form = as_posted(EXAMPLE, display__pools__name=names, display__pools__pages=pages)
    assert words in cf.apply(EXAMPLE, form).errors["display.pools"]


def test_a_config_without_a_display_block_saves_without_one():
    e = edit("server:\n  port: 8080\n", server__port="9090")
    assert e.text == "server:\n  port: 9090\n"


def _settings(config: dict):
    """load_settings(config) in a form two calls can be compared by."""
    s = load_settings(config)
    schedule = s.core.server.schedule
    server = dataclasses.replace(s.core.server, schedule=None)
    return (dataclasses.replace(s, core=dataclasses.replace(s.core, server=server),
                                dock_sync=None, head_sync=None),
            type(schedule).__name__, vars(getattr(schedule, "pools")),
            s.dock_sync.describe(), s.head_sync.describe())


def _with(config: dict, path: tuple, value) -> dict:
    out = dict(config)
    node = out
    for k in path[:-1]:
        node[k] = dict(node.get(k) or {})
        node = node[k]
    node[path[-1]] = value
    return out


BASE = {"display": {"pools": {"co2": ["breathe.png"]},
                    "schedule": {"type": "timeranges", "ranges": DEFAULT_PAGE_RANGES}}}


@pytest.mark.parametrize("f", [f for f in cf.FIELDS if f.default is not None and f.kind != "window"
                               and not callable(f.default)], ids=lambda f: f.key)
def test_a_fields_default_is_what_the_server_takes_without_the_key(f):
    assert _settings(_with(BASE, f.path, f.default)) == _settings(BASE)


@pytest.mark.parametrize("key, base", [
    ("image.innerWidth", BASE), ("image.innerHeight", BASE),
    ("display.schedule.order", BASE),
])
def test_a_default_worked_out_from_the_config_is_what_the_server_takes(key, base):
    f = cf.BY_KEY[key]
    assert _settings(_with(base, f.path, cf.default_of(f, base))) == _settings(base)


def test_an_unset_field_shows_its_default_as_its_value():
    shown = cf.shown({"image": {"width": 1600}})
    assert (shown["server.port"], shown["image.innerWidth"], shown["server.timezone"]) == (
        "8080", "1600", cf.host_zone())
    assert cf.defaults({})["server.port"] == "8080"


def test_every_field_is_named_once_and_every_condition_names_a_field():
    assert len(cf.BY_KEY) == len(cf.FIELDS)
    for f in cf.FIELDS:
        if f.when:
            assert f.when.split("=")[0] in cf.BY_KEY, f.key


def test_changes_are_in_words_with_each_schedule_on_one_line():
    old = cf.read(EXAMPLE)
    new = cf.read(edit(server__port="9090", dock__led__schedule="true",
                       dock__sync__from=["01:00", "07:00", "22:00"],
                       dock__sync__every=["30", "5", "0"]).text)
    assert cf.changes(old, new) == [
        {"name": "Server · Port", "old": "8080", "new": "9090"},
        {"name": "Dock · Sync schedule", "old": "01:00 every 30 min · 07:00 every 5 min",
         "new": "01:00 every 30 min · 07:00 every 5 min · 22:00 off"},
        {"name": "Dock · Schedule", "old": "all day", "new": "07:00–01:00"},
    ]


def test_a_change_to_the_looks_reads_as_one_line():
    new = cf.read(looks(EXAMPLE, ("no_wifi", "flash", "1"), ("well", "solid", "1")).text)
    assert cf.changes(cf.read(EXAMPLE), new) == [
        {"name": "Dock · Patterns",
         "old": "Starting pulse 0.5 s · No Wi-Fi flash 1 s · Post failed flash 2 s · "
                "Sensor missing flash 3 s · Well pulse 1 s",
         "new": "No Wi-Fi flash 1 s · Well solid"}]


def test_a_changed_double_or_triple_reads_by_its_name():
    new = cf.read(looks(EXAMPLE, ("well", "triple_pulse", "1.9")).text)
    assert cf.changes(cf.read(EXAMPLE), new)[0]["new"] == "Well triple pulse 1.9 s"


@pytest.mark.parametrize("path, name", [
    (("server", "port"), "Server · Port"),
    (("status", "keep_days"), "Storage · Board reports · Delete after"),
    (("image", "innerWidth"), "Image · Drawn area · Width"),
    (("display", "pools", "co2"), "Display · Pools · co2"),
])
def test_a_label_two_fields_share_is_named_with_its_group(path, name):
    assert cf.name_of(path) == name


@pytest.mark.parametrize("message, where", [
    ("server.port must be 65535 or less. It is 70000.", ("server.port", "server")),
    ("display.pools name radon.png, which no page produces", ("display.pools", "display")),
    ("display.schedule: '7' is not a valid time", (None, "display")),
    ("client.firmware.product is required when it is enabled", (None, "firmware")),
    ("It is not YAML: bad", (None, None)),
])
def test_a_problem_is_placed_by_the_key_it_names(message, where):
    assert cf.locate(message) == where


def test_the_edit_reads_back_as_pyyaml_reads_it():
    e = edit(server__timezone="Europe/London", mqtt__enabled="true", site__altitude_m="12.5")
    cfg = yaml.safe_load(e.text)
    assert (cfg["server"]["timezone"], cfg["mqtt"]["enabled"], cfg["site"]["altitude_m"]) == (
        "Europe/London", True, 12.5)


def test_a_field_named_by_its_place_on_the_page_has_its_full_name_in_messages():
    assert cf.name_of(("dock", "led", "schedule", "from")) == "Dock · Schedule from"
    assert cf.name_of(("dock", "sync")) == "Dock · Sync schedule"
