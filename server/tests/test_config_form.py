"""The config form: what a filled-in form writes into config.yaml, and what it leaves."""
import dataclasses
import os

import pytest
import yaml
from werkzeug.datastructures import MultiDict

import config_form as cf
from server import load_settings

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


def test_quiet_hours_off_are_an_empty_block():
    e = edit(posts__quiet="false")
    assert "  quiet: {}         # a slower cadence overnight" in e.text
    assert cf.read(e.text)["posts"]["quiet"] == {}


def test_quiet_hours_back_on_at_the_defaults_take_the_block_out():
    off = edit(posts__quiet="false").text
    e = edit(off, posts__quiet="true")
    assert "quiet" not in cf.read(e.text)["posts"]


def test_quiet_hours_from_the_defaults_write_the_whole_block_quoted():
    text = EXAMPLE.replace('  quiet:            # a slower cadence overnight, in '
                           'server.timezone; `quiet: {}` turns it off\n    from: "01:00"\n'
                           '    to: "07:00"\n    every: 1800\n', "")
    assert "quiet" not in cf.read(text)["posts"]
    e = edit(text, posts__quiet__to="06:30")
    assert '    from: "01:00"\n    to: "06:30"\n    every: 1800\n' in e.text
    assert cf.read(e.text)["posts"]["quiet"] == {"from": "01:00", "to": "06:30", "every": 1800}


def test_a_quiet_time_is_quoted_so_pyyaml_reads_a_string():
    e = edit(posts__quiet__from="23:30")
    assert '    from: "23:30"' in e.text
    assert cf.read(e.text)["posts"]["quiet"]["from"] == "23:30"


def test_pools_change_come_and_go_and_keep_their_order():
    e = edit(display__pools__name=["comfort", "co2", "extra"],
             display__pools__pages=["comfort.png", "breathe.png, co2-trace.png", "day.png"])
    assert cf.read(e.text)["display"]["pools"] == {
        "comfort": ["comfort.png"], "co2": ["breathe.png", "co2-trace.png"], "extra": ["day.png"]}
    assert list(cf.read(e.text)["display"]["pools"]) == ["comfort", "co2", "extra"]
    assert "    co2: [breathe.png, co2-trace.png]" in e.text
    assert "  schedule:\n    type: interval" in e.text


def test_a_times_schedule_quotes_its_times_and_drops_the_interval():
    e = edit(display__schedule__type="times",
             display__schedule__times__at=["19:30", "07:00:00"],
             display__schedule__times__pool=["co2", "day"])
    sched = cf.read(e.text)["display"]["schedule"]
    assert sched == {"type": "times", "reshuffle_hours": 3, "19:30:00": "co2", "07:00:00": "day"}
    back = edit(e.text, display__schedule__type="interval", display__schedule__every="600")
    assert cf.read(back.text)["display"]["schedule"] == {"type": "interval", "reshuffle_hours": 3,
                                                         "every": 600}


def test_a_field_an_environment_variable_sets_is_left_alone(monkeypatch):
    monkeypatch.setenv("SERVER_PORT", "7070")
    e = cf.apply(EXAMPLE, MultiDict({"server.port": "1234"}))
    assert e.text == EXAMPLE and e.changed == []


@pytest.mark.parametrize("key, value, words", [
    ("server.port", "abc", "whole number"),
    ("server.port", "70000", "at most 65535"),
    ("posts.every", "90", "multiple of 60"),
    ("posts.quiet.from", "25:00", "HH:MM"),
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
    return (dataclasses.replace(s, core=dataclasses.replace(s.core, server=server), posts=None),
            type(schedule).__name__, vars(getattr(schedule, "pools")), vars(s.posts))


def _with(config: dict, path: tuple, value) -> dict:
    out = dict(config)
    node = out
    for k in path[:-1]:
        node[k] = dict(node.get(k) or {})
        node = node[k]
    node[path[-1]] = value
    return out


BASE = {"display": {"pools": {"co2": ["breathe.png"]},
                    "schedule": {"type": "interval", "every": 300}}}


@pytest.mark.parametrize("f", [f for f in cf.FIELDS if f.default is not None and f.kind != "quiet"
                               and not callable(f.default)], ids=lambda f: f.key)
def test_a_fields_default_is_what_the_server_takes_without_the_key(f):
    assert _settings(_with(BASE, f.path, f.default)) == _settings(BASE)


QUIET = _with(BASE, ("posts", "quiet"), {"from": "01:00", "to": "07:00"})


@pytest.mark.parametrize("key, base", [
    ("image.innerWidth", BASE), ("image.innerHeight", BASE),
    ("display.schedule.order", BASE), ("posts.quiet.every", QUIET),
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


def test_changes_are_in_words_with_quiet_hours_on_one_line():
    old = cf.read(EXAMPLE)
    new = cf.read(edit(server__port="9090", posts__quiet="false").text)
    assert cf.changes(old, new) == [
        {"name": "Server · Port", "old": "8080", "new": "9090"},
        {"name": "Boards · Quiet hours", "old": "01:00–07:00, 1800 s", "new": "off"},
    ]


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
