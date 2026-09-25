"""config.yaml in the browser: a form in tabs, the file as text, a check, a
save and a restart.

    GET  /web/config     the form, and the file as text in the last tab
    GET  /web/config/export/<store>
                         everything one store holds, a JSON document a line
    POST /web/config/import/<store>
                         such a file back into that store, all of it or none;
                         replace=true puts it over the records that exist
    POST /web/config     mode=form: the form's values written into the file
                         mode=yaml: the text as given
                         mode=restore: config.yaml.bak
                         mode=recalibrate: the dock's SCD41 recalibrated to
                              ppm at its next reading; no action, no restart
                         then action=check: whether that would start the server
                              action=review: the same, and what it changes, as JSON
                              action=save: the same check, then the old file kept
                              as config.yaml.bak, the new one written, and the
                              server restarted on it

Nothing guards these routes yet: anyone who can reach the server can change
its config.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import zoneinfo
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from airium import Airium
from epd_server.timeranges import MAX_RANGES
from flask import Blueprint, Response, abort, jsonify, redirect, request
from markupsafe import Markup

import config_form as cf
import dock_settings as ds
from html_doc import Html
from pages.base import EnvPage
from metrics import age_span
from transfer import Corrupt, Overlap, Transfer
from web import menu_bar, page_head

# The most an imported file may weigh.
MAX_UPLOAD = 64 * 1024 * 1024
# The browse page's URL from /web/config, once the server answers again.
BROWSE_HREF = "./"
YAML_TAB = "yaml"
TAB_NAMES = [t.name for t in cf.TABS] + [YAML_TAB]

# What each drawing on a sheet shows, and how to change it by dragging.
VISUAL_CAPTIONS = {
    "dial": "Each tick is a sync. Hatching marks a time range that is off. "
            "Drag a time range's start to move it.",
    "panel": "The image, with the drawn area hatched. "
             "Drag the round handle to resize it; click a dot to move it.",
    "slot": "The time before one sync. "
            "Drag the fan band's left edge; past the start, the fan never stops.",
}

# What a check or a save that changed nothing says, as a dialog's heading,
# its line, and whether it offers the save. Without scripts the note stays a
# banner.
NOTICES = {
    "No problems found.": ("No problems found", "Save and restart to apply it.", True),
}

# One wording for the state, whether it is a banner or a refused save.
READ_ONLY = "config.yaml is read-only. Change its permissions to save."


def save(path: str, text: str) -> None:
    """Keep ``path`` as it was beside it, then write ``text`` over it in place.

    In place, because a file mounted into a container on its own cannot be
    replaced by a rename.
    """
    shutil.copyfile(path, path + ".bak")
    with open(path, "w") as f:
        f.write(text if text.endswith("\n") else text + "\n")


@dataclass
class Report:
    """What an import did, shown under the row that did it."""
    store: str = ""
    words: str = ""
    bad: bool = False


@dataclass
class View:
    """What the config page shows."""
    text: str                       # the YAML tab's text
    file_text: str                  # the file as it is
    values: dict[str, Any]          # each field as its input shows it
    initial: dict[str, Any]         # the same from the file: what a change is measured against
    defaults: dict[str, str] = field(default_factory=dict)   # each default, as its input shows it
    errors: dict[str, str] = field(default_factory=dict)
    problem: str = ""
    note: str = ""
    status: str = ""                # the save bar's words, when no note says more
    tab: str = ""                   # the tab to open; empty lets the URL choose
    unreadable: str = ""            # why the form cannot show this file
    sizes: dict[str, int] = field(default_factory=dict)      # store -> the download's bytes
    report: Report = field(default_factory=Report)
    dock: DockState | None = None
    head: dict | None = None        # the head's panel as it reports it: width, height, board


@dataclass
class DockState:
    """What the Dock tab says about the dock beside its settings."""
    applied: bool | None = None     # runs the saved settings; None before it says
    refused: list[str] = field(default_factory=list)
    pending: dict | None = None     # a recalibration it has yet to run
    last: dict | None = None        # its report of the last one it ran
    ppm: str = str(ds.RECALIBRATE_MIN_PPM + 20)
    offline: bool = False           # it has missed two slots; nothing on the tab reaches it
    age_s: int | None = None        # since its last sync
    expired: dict | None = None     # a recalibration that lapsed before the dock ran it
    next_sync: str = ""             # the local time of its next slot, HH:MM


def head_panel(entry: dict | None) -> dict | None:
    """The head's panel from its newest report: width, height and board, or
    None before it has said."""
    client = ((entry or {}).get("doc") or {}).get("client") or {}
    panel = client.get("head") or {}
    width, height = panel.get("width"), panel.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        return None
    return {"width": width, "height": height, "board": str(client.get("board") or "")}


def dock_state(dock: ds.BoardSettings) -> DockState:
    applied, refused = dock.applied()
    offline, age = dock.offline()
    return DockState(applied, refused, dock.pending(), dock.last_recalibration(),
                     offline=offline, age_s=age, expired=dock.expired(),
                     next_sync=dock.next_sync())


def file_view(text: str) -> View:
    try:
        cfg = cf.read(text)
    except cf.FormError as exc:
        values = cf.shown({})
        return View(text, text, values, dict(values), tab=YAML_TAB,
                    unreadable=str(exc))
    values = cf.shown(cfg)
    return View(text, text, values, dict(values), cf.defaults(cfg))


def _id(key: str) -> str:
    return "f-" + key.replace(".", "-")


def _when(t: datetime) -> str:
    return f"{t:%a} {t.day} {t:%b}, {t:%H:%M}"


def _pool_names(view: View) -> list[str]:
    return [n for n, _ in view.values.get("display.pools", []) if n.strip()]


def _pool_row(a: Airium, key: str, name: str, pages: str, images: list[str]) -> None:
    with a.div(klass="row"):
        a.input(type="text", klass="pool-name", name=key + ".name", value=name,
                placeholder="name", spellcheck="false", autocomplete="off",
                **{"aria-label": "Pool name"})
        a.input(type="text", klass="chips", name=key + ".pages", value=pages,
                spellcheck="false", autocomplete="off", placeholder="breathe.png, co2-trace.png",
                **{"aria-label": "Images", "data-options": " ".join(images)})
        a.button(type="button", klass="remove", _t="×", **{"aria-label": "Remove this pool"})


# A clock face in the ink of the button it is on.
CLOCK_ICON = Markup('<svg viewBox="0 0 16 16" aria-hidden="true">'
                    '<circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" '
                    'stroke-width="1.5"/><path d="M8 4.5V8l2.25 1.5" fill="none" '
                    'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
                    'stroke-linejoin="round"/></svg>')


def _time_input(a: Airium, **attrs) -> None:
    """A time input, and the button that opens the page's own picker
    (timepick.js): the browser's takes its colours from the system."""
    lock = {"disabled": "disabled"} if "disabled" in attrs else {}
    with a.span(klass="time"):
        a.input(type="time", **attrs)
        a.button(type="button", klass="pick", _t=CLOCK_ICON,
                 **{"aria-label": "Choose a time", "aria-expanded": "false"}, **lock)


def _clock_row(a: Airium, key: str, start: str, every: str, locked: bool) -> None:
    lock = {"disabled": "disabled"} if locked else {}
    with a.div(klass="row"):
        _time_input(a, name=key + ".from", value=start, **{"aria-label": "From"}, **lock)
        with a.span(klass="every"):
            a.input(type="number", name=key + ".every", value=every, min="0",
                    max=str(24 * 60), step="1", inputmode="numeric",
                    **{"aria-label": "Every, in minutes"}, **lock)
            a.span(klass="unit", _t="min")
        a.button(type="button", klass="remove", _t="×",
                 **{"aria-label": "Remove this time range; the one before takes its hours"},
                 **lock)


def _look_row(a: Airium, key: str, trigger: str, pattern: str, length: str,
              locked: bool) -> None:
    lock = {"disabled": "disabled"} if locked else {}
    with a.div(klass="row"):
        with a.select(name=key + ".trigger", **{"aria-label": "Trigger"}, **lock):
            for t, words in cf.LED_TRIGGER_LABELS.items():
                a.option(value=t, _t=words, **({"selected": "selected"} if t == trigger else {}))
        with a.select(name=key + ".pattern", **{"aria-label": "Pattern"}, **lock):
            for p, words in cf.LED_PATTERN_LABELS.items():
                a.option(value=p, _t=words, **({"selected": "selected"} if p == pattern else {}))
        # Off and solid keep their length, unseen, so each row posts all three.
        with a.span(klass="length idle" if pattern in ds.LED_STILL else "length"):
            a.input(type="number", name=key + ".length_s", value=length,
                    min=f"{ds.led_min_length(pattern):g}", max=f"{ds.LED_LENGTH_MAX_S:g}",
                    step="any", inputmode="decimal", **{"aria-label": "Length, in seconds"},
                    **lock)
            a.span(klass="unit", _t="s")
        a.button(type="button", klass="remove", _t="×",
                 **{"aria-label": "Remove this pattern; its trigger is skipped"}, **lock)


def _row(a: Airium, f: cf.Field, cells: tuple, images: list[str], locked: bool) -> None:
    if f.kind == "pools":
        _pool_row(a, f.key, *cells, images)
    elif f.kind == "clock":
        _clock_row(a, f.key, *cells, locked)
    else:
        _look_row(a, f.key, *cells, locked)


# What a new row starts as: a look takes its trigger's default once it has one.
BLANK_ROWS = {"looks": ("", "pulse", "1")}
# The words on each field's button that adds a row.
ADD_WORDS = {"pools": "Add a pool", "clock": "Add a time range", "looks": "Add a pattern"}


def _rows(a: Airium, f: cf.Field, view: View, images: list[str], heading: str,
          locked: bool = False) -> None:
    """A field of rows. ``locked`` applies to the Dock tab's rows, the only
    ones on a tab that locks."""
    rows = view.values.get(f.key, [])
    marks = {"data-max": str(MAX_RANGES)} if f.kind == "clock" else {}
    if f.kind == "looks":
        marks = {"data-looks": json.dumps({t: [p, f"{n:g}"] for t, p, n in ds.LED_LOOKS},
                                          separators=(",", ":")),
                 "data-min": json.dumps({p: f"{ds.led_min_length(p):g}" for p in ds.LED_PATTERNS
                                         if p not in ds.LED_STILL}, separators=(",", ":"))}
    with a.fieldset(klass=f"rows {f.kind}", id=_id(f.key),
                    **{"data-key": f.key, "data-initial": cf.initial(view.initial[f.key])},
                    **marks):
        a.legend(klass="name hide" if f.label == heading else "name", _t=f.label)
        # With the rows locked, the key goes unposted and the file's value stands.
        a.input(type="hidden", name=f.key, value="1", **({"disabled": "disabled"} if locked else {}))
        if f.kind == "looks":
            # The selects and inputs name themselves; these are for the eye.
            with a.div(klass="heads", **{"aria-hidden": "true"}):
                for words in ("Trigger", "Pattern", "Length"):
                    a.span(_t=words)
        with a.div(klass="list"):
            for cells in rows:
                _row(a, f, cells, images, locked)
        with a.template():
            _row(a, f, BLANK_ROWS.get(f.kind, ("", "")), images, locked)
        with a.div(klass="foot"):
            if f.kind in ADD_WORDS:
                a.button(type="button", klass="add", _t=ADD_WORDS[f.kind],
                         **({"disabled": "disabled"} if locked else {}))
            if f.help:
                a.p(klass="help", _t=f.help)


def _control(a: Airium, f: cf.Field, view: View, env: str | None, locked: bool) -> None:
    value = view.values.get(f.key, "")
    if env is not None and f.scale != 1 and env.strip().isdigit():
        env = cf.input_text(f, int(env))
    lock = {"disabled": "disabled"} if env is not None or locked else {}
    marks = {"data-default": view.defaults[f.key]} if f.key in view.defaults else {}
    own = {"id": _id(f.key), "name": f.key, "data-key": f.key,
           "data-initial": cf.initial(view.initial.get(f.key, "")), **lock, **marks}
    with a.div(klass="control"):
        if f.kind == "choice":
            chosen = env if env is not None else value
            with a.div(klass="segments", role="radiogroup", id=_id(f.key),
                       **{"aria-labelledby": _id(f.key) + "-name", "data-key": f.key,
                          "data-initial": view.initial.get(f.key, "")}, **marks):
                for choice, words in f.choices:
                    with a.label():
                        a.input(type="radio", name=f.key, value=choice, **lock,
                                **({"checked": "checked"} if choice == chosen else {}))
                        a.span(_t=words)
        elif f.kind in ("bool", "window"):
            on = (env or "").strip().lower() in ("1", "true", "yes", "on") if env is not None \
                else value == "true"
            a.input(type="hidden", name=f.key, value="false", **lock)
            a.input(type="checkbox", klass="switch", value="true", **own,
                    **({"checked": "checked"} if on else {}))
            a.span(klass="state", **{"aria-hidden": "true"})
        else:
            attrs: dict[str, Any] = {"value": env if env is not None else value}
            if f.hint:
                attrs["placeholder"] = f.hint
            if f.kind in ("int", "number"):
                attrs.update(type="number", step=str(f.step) if f.kind == "int" else "any",
                             inputmode="numeric" if f.kind == "int" else "decimal")
                if f.minimum is not None:
                    attrs["min"] = f"{f.minimum:g}"
                if f.maximum is not None:
                    attrs["max"] = f"{f.maximum:g}"
            elif f.kind != "time":
                attrs.update(type="text", spellcheck="false", autocomplete="off")
                if f.kind == "zone":
                    attrs["list"] = "zones"
                if f.kind == "order":
                    attrs.update(klass="chips",
                                 **{"data-options": " ".join(_pool_names(view)),
                                    "data-options-from": "display.pools"})
            if f.kind == "time":
                _time_input(a, **own, **attrs)
            else:
                a.input(**own, **attrs)
            if f.unit:
                a.span(klass="unit", _t=f.unit)


def _reset_button(a: Airium, f: cf.Field, view: View) -> None:
    """Puts the default back; it shows once the value differs from it."""
    at_default = view.values.get(f.key) == view.defaults[f.key]
    a.button(type="button", klass="reset", _t="Reset",
             **{"aria-label": f"Reset {f.label}"}, **({"hidden": "hidden"} if at_default else {}))


def _field(a: Airium, f: cf.Field, view: View, images: list[str], heading: str,
           locked: bool = False, sheet: bool = False, by_position: bool = False) -> None:
    """One setting. ``locked`` shows it and keeps it from being changed, as
    an environment variable does, but leaves the file's value standing. On a
    ``sheet`` a dotted leader runs from its name to its value. ``by_position``
    marks a choice the group's position grid stands in for once scripts run."""
    env = f.env_value()
    error = view.errors.get(f.key)
    klass = "field by-position" if by_position else "field"
    if f.kind in cf.ROWS:
        klass += " wide"
    if error:
        klass += " invalid"
    with a.div(klass=klass, **{"data-field": f.key}, **({"data-when": f.when} if f.when else {})):
        if f.kind in cf.ROWS:
            _rows(a, f, view, images, heading, locked)
        else:
            with a.div(klass="head"):
                if f.kind == "choice":
                    a.span(klass="name", id=_id(f.key) + "-name", _t=f.label)
                else:
                    a.label(klass="name", for_=_id(f.key), _t=f.label)
                if f.key in view.defaults and env is None and not locked:
                    _reset_button(a, f, view)
            if sheet:
                a.span(klass="leader", **{"aria-hidden": "true"})
            _control(a, f, view, env, locked)
        if f.help and f.kind not in cf.ROWS:
            a.p(klass="help", _t=f.help)
        if env is not None:
            a.p(klass="env", _t=f"Set by {f.env_name}")
        if error:
            a.p(klass="error", id="e-" + _id(f.key)[2:], _t=error)


def _size(count: int) -> str:
    """A download's size, near enough to choose by."""
    if count <= 0:
        return "empty"
    if count < 1000:
        return f"≈ {count} bytes"
    if count < 1_000_000:
        return f"≈ {count / 1000:.0f} kB"
    return f"≈ {count / 1_000_000:.1f} MB"


def _export(a: Airium, store: str, size: int) -> None:
    """The row that downloads a store, greyed out while it holds nothing."""
    with a.div(klass="field", **{"data-export": store}):
        with a.div(klass="head"):
            a.span(klass="name", _t="Export")
        with a.div(klass="control"):
            a.a(klass="button" if size else "button off", _t="Download",
                **({"href": f"config/export/{store}", "download": "download"} if size
                   else {"aria-disabled": "true"}))
            a.span(klass="unit", _t=_size(size) if size else "No records yet.")


def _import(a: Airium, store: str, report: Report) -> None:
    """The row that takes a file back in. Its controls belong to the form
    beside the settings form, because a form cannot hold another."""
    form = f"import-{store}"
    with a.div(klass="field", **{"data-import": store}):
        with a.div(klass="head"):
            a.label(klass="name", for_=f"file-{store}", _t="Import")
        with a.div(klass="control"):
            a.input(type="file", id=f"file-{store}", name="file", form=form,
                    accept=".jsonl,application/x-ndjson")
            with a.label(klass="over"):
                a.input(type="checkbox", name="replace", value="true", form=form)
                a.span(_t="Replace")
            a.button(type="submit", klass="button", form=form, _t="Upload")
        if report.store == store:
            a.p(klass="error" if report.bad else "help", _t=report.words)


def _settings_line(a: Airium, state: DockState) -> None:
    """Whether the dock runs the saved settings, as a banner across the tab:
    a pill naming the state, then what it means. config.js puts a new one in
    its place from GET /web/config/live."""
    last = Markup("Last sync {} ago.").format(age_span(state.age_s or 0))
    if state.offline:
        pill = ("offline", "Offline", last + " Settings unlock when the dock syncs again.")
    elif state.applied is None:
        pill = None
    elif state.applied:
        pill = ("synced", "Synchronized", last)
    else:
        pill = ("waiting", "Not synchronized",
                f"The dock takes these settings before its next sync, "
                f"at {state.next_sync}.")
    with a.div(klass="dock-state", id="dock-state",
               **{"data-offline": "true" if state.offline else "false"}):
        with a.p(klass="banner dock-line", id="dock-applied"):
            if pill is None:
                a.span(_t="No sync from the dock yet. Settings apply once it connects.")
            else:
                klass, name, words = pill
                a.span(klass=f"pill {klass}", id=f"dock-{klass}", _t=name)
                a.span(_t=words)
        if state.refused:
            names = ", ".join(_label_of(("dock", *key.split("."))) for key in state.refused)
            a.p(klass="error", id="dock-refused",
                _t=f"Refused by the dock: {names}. Check the dock's firmware version.")


def _label_of(path: tuple) -> str:
    """A setting's name as its own tab shows it."""
    f = cf.field_at(path)
    return (f.long or f.label) if f else ".".join(path)


def _recalibration_words(state: DockState) -> str:
    if state.pending:
        asked = datetime.fromtimestamp(state.pending["id"])
        lapses = datetime.fromtimestamp(state.pending["id"] + ds.RECALIBRATE_WITHIN_S)
        return (f"Waiting for the dock's next sync: {state.pending['ppm']} ppm, "
                f"asked {_when(asked)}. Expires at {lapses:%H:%M}.")
    if state.expired:
        return (f"Recalibration to {state.expired['ppm']} ppm expired: "
                "the dock did not sync within an hour.")
    last = state.last
    if not last:
        return ("Keep the dock in air of a known CO₂ level for 3 minutes, then enter that level. "
                "Outdoor air is about 420 ppm.")
    asked = _when(datetime.fromtimestamp(last["id"]))
    if not last.get("ok"):
        return (f"Last recalibration failed: {last.get('ppm', '?')} ppm, asked {asked}. "
                "The SCD41 refused it. Try again once the dock has been in that air "
                "for 3 minutes.")
    correction = last.get("correction_ppm", 0)
    return (f"Last recalibration: {last.get('ppm', '?')} ppm, asked {asked}. "
            f"Corrected by {correction:+d} ppm.")


def _recalibrate(a: Airium, state: DockState, report: Report, sheet: bool = False) -> None:
    """The row that asks for a recalibration. Its controls belong to the form
    beside the settings form, as the import rows' do."""
    form = "recalibrate-form"
    lock = {"disabled": "disabled"} if state.offline else {}
    with a.div(klass="field wide", **{"data-recalibrate": "scd41"}):
        with a.div(klass="head"):
            a.label(klass="name", for_="recalibrate-ppm", _t="Recalibrate")
        if sheet:
            a.span(klass="leader", **{"aria-hidden": "true"})
        with a.div(klass="control"):
            a.input(type="number", id="recalibrate-ppm", name="ppm", form=form,
                    value=state.ppm, step="1", inputmode="numeric",
                    min=str(ds.RECALIBRATE_MIN_PPM), max=str(ds.RECALIBRATE_MAX_PPM), **lock)
            a.span(klass="unit", _t="ppm")
            a.button(type="submit", klass="button", form=form, _t="Recalibrate", **lock)
        if report.store == "recalibrate":
            a.p(klass="error" if report.bad else "help", _t=report.words)
        else:
            a.p(klass="help", id="recalibrate-state", _t=_recalibration_words(state))


def _savebar(a: Airium, writable: bool, status: str, *, discard: bool) -> None:
    with a.footer(klass="savebar"):
        a.p(klass="status", _t=status, **{"aria-live": "polite",
                                          "data-idle": "No changes."})
        with a.div(klass="choice"):
            if discard:
                a.a(klass="button discard", href="config", _t="Discard")
            a.button(type="submit", name="action", value="check", _t="Check")
            a.button(type="submit", name="action", value="save", klass="primary",
                     _t="Save and restart", **({} if writable else {"disabled": "disabled"}))


@contextlib.contextmanager
def _nothing():
    yield


def _place_words(x: str, y: str) -> str:
    """"Top left", "Centre right", "Centre": a grid square's name."""
    across = {"left": "left", "center": "centre", "right": "right"}[x]
    down = {"top": "Top", "center": "Centre", "bottom": "Bottom"}[y]
    return "Centre" if x == y == "center" else f"{down} {across}"


def _position(a: Airium, g: cf.Group, view: View, locked: bool) -> None:
    """A 3 × 3 grid that sets the group's two alignments, across and up and
    down, with one click. It stands in for their two rows of choices, which
    stay in the form as what a save sends."""
    across, down = [f for f in g.fields if f.kind == "choice"]
    x = view.values.get(across.key) or "center"
    y = view.values.get(down.key) or "center"
    lock = {"disabled": "disabled"} if locked or across.env_value() or down.env_value() else {}
    with a.div(klass="field position"):
        with a.div(klass="head"):
            a.span(klass="name", id="position-name", _t="Position")
        a.span(klass="leader", **{"aria-hidden": "true"})
        with a.div(klass="control"):
            with a.div(klass="grid3", role="group",
                       **{"aria-labelledby": "position-name", "data-x": across.key,
                          "data-y": down.key}):
                for yv in ("top", "center", "bottom"):
                    for xv in ("left", "center", "right"):
                        a.button(type="button", _t="", **lock,
                                 **{"data-x": xv, "data-y": yv,
                                    "aria-label": _place_words(xv, yv),
                                    "aria-pressed": "true" if (xv, yv) == (x, y) else "false"})


def _head_size(a: Airium, view: View) -> None:
    """The size the head reports, against the saved one."""
    head = view.head
    if not head:
        return
    said = f"{head['width']} × {head['height']} px"
    if head.get("board"):
        said += f", {head['board']}"
    try:
        saved = (int(view.initial["image.width"]), int(view.initial["image.height"]))
    except (KeyError, ValueError):
        saved = None
    if saved == (head["width"], head["height"]):
        a.p(klass="help head-size", id="head-size", _t=f"The head reports {said}.")
    else:
        a.p(klass="error head-size", id="head-size",
            _t=f"Not the head's size: it reports {said}. Set Width and Height to match.")


def _runs(fields: tuple[cf.Field, ...], sheet: bool) -> list[tuple[str, list[cf.Field]]]:
    """The fields in order, those in a row that show only while another field
    holds a value run together under that ``when``, on a sheet, so two or
    more can share one box. Elsewhere each field stands alone."""
    runs: list[tuple[str, list[cf.Field]]] = []
    for f in fields:
        when = f.when if sheet else ""
        if when and runs and runs[-1][0] == when:
            runs[-1][1].append(f)
        else:
            runs.append((when, [f]))
    return runs


def _group(a: Airium, g: cf.Group, view: View, images: list[str], locked: bool,
           sheet: bool = False) -> None:
    """A group's heading, the line under it that says what the group is for,
    and its fields. On a ``sheet`` a heading such as "CO₂ · SCD41" takes two
    lines, the part under the measurement, the heading and its line keep to
    their column, and the group's drawing, when it has one, comes before its
    fields."""
    with a.div(klass="heading") if sheet else _nothing():
        if g.heading and sheet and " · " in g.heading:
            title, part = g.heading.split(" · ", 1)
            with a.h2(klass="group label"):
                a.span(_t=title)
                a.span(klass="part", _t=part)
        elif g.heading:
            a.h2(klass="group label", _t=g.heading)
        if g.heading and g.about:
            a.p(klass="about", _t=g.about)
    with a.div(klass=f"content visual-{g.visual}" if g.visual else "content") if sheet \
            else _nothing():
        if sheet and g.visual:
            # A dial draws the schedule its group holds.
            key = next((f.key for f in g.fields if f.kind == "clock"), "")
            with a.div(klass="visual"):
                a.canvas(id="-".join(["visual", g.visual, *key.split(".")]) if key
                         else f"visual-{g.visual}",
                         **{"data-visual": g.visual, "aria-hidden": "true"},
                         **({"data-schedule": key} if key else {}))
                a.p(klass="caption", _t=g.caption or VISUAL_CAPTIONS[g.visual])
        with a.div(klass="fields"):
            for when, fields in _runs(g.fields, sheet):
                boxed = when and len(fields) > 1
                with a.div(klass="subsection", **{"data-when": when}) if boxed else _nothing():
                    for f in fields:
                        _field(a, f, view, images, g.heading, locked, sheet,
                               by_position=g.action == "position" and f.kind == "choice")
            if g.action == "position":
                _position(a, g, view, locked)
            if g.action == "head":
                _head_size(a, view)
            if g.store in view.sizes:
                _export(a, g.store, view.sizes[g.store])
                _import(a, g.store, view.report)
            if g.action == "recalibrate" and view.dock is not None:
                _recalibrate(a, view.dock, view.report, sheet)


def _tab_problems(view: View) -> set[str]:
    tabs = {cf.TAB_OF[k] for k in view.errors if k in cf.TAB_OF}
    if view.problem and view.tab and view.tab != YAML_TAB:
        tabs.add(view.tab)
    return tabs


def config_html(pages: list[EnvPage], view: View, writable: bool,
                bak: datetime | None = None) -> str:
    images = [p.png_filename for p in pages]
    tabs = [] if view.unreadable else [(t.name, t.title) for t in cf.TABS]
    tabs.append((YAML_TAB, "YAML"))
    marked = _tab_problems(view)
    status = view.note or view.status or (
        "Not saved." if view.problem or view.errors else "No changes.")
    a = Html()
    a("<!DOCTYPE html>")
    with a.html(lang="en"):
        page_head(a, "Canary · Config")
        with a.body(klass="web config"):
            menu_bar(a, pages, BROWSE_HREF, "config")
            with a.main(klass="settings"):
                with a.div(klass="top"):
                    a.h1(klass="title label", _t="Config")
                    with a.div(klass="where"):
                        if bak is not None and writable:
                            with a.form(method="post", action="config", klass="restore",
                                        id="restore-form",
                                        **{"data-title": "Restore the previous version?",
                                           "data-confirm": "Restore and restart"}):
                                a.input(type="hidden", name="mode", value="restore")
                                a.span(klass="stamp", _t=f"Last saved {_when(bak)}")
                                a.button(type="submit", name="action", value="save",
                                         klass="link", _t="Restore")
                with a.nav(klass="tabs", role="tablist", **{"aria-label": "Sections"},
                           **({"data-open": view.tab} if view.tab else {})):
                    for name, title in tabs:
                        a.a(href=f"#{name}", id=f"tab-{name}", role="tab",
                            klass="tab problem" if name in marked else "tab",
                            _t=title, **{"data-tab": name, "aria-controls": f"panel-{name}"})
                if not writable:
                    a.p(klass="banner", id="read-only",
                        _t=READ_ONLY)
                if view.unreadable:
                    a.p(klass="banner problem", id="unreadable", _t=view.unreadable)
                if view.problem:
                    a.p(klass="banner problem", id="problem", _t=f"Not saved: {view.problem}")
                if view.note:
                    a.p(klass="banner", id="note", _t=view.note)
                if not view.unreadable:
                    with a.form(method="post", action="config", id="settings-form",
                                novalidate="novalidate",
                                **{"data-title": "Save and restart?",
                                   "data-confirm": "Save and restart"}):
                        a.input(type="hidden", name="mode", value="form")
                        a.input(type="hidden", name="tab", value=view.tab or cf.TABS[0].name)
                        for t in cf.TABS:
                            with a.section(klass="panel sheet" if t.sheet else "panel",
                                           id=f"panel-{t.name}", role="tabpanel",
                                           **{"data-tab": t.name,
                                              "aria-labelledby": f"tab-{t.name}"}):
                                locked = False
                                if t.name == "dock" and view.dock is not None:
                                    _settings_line(a, view.dock)
                                    locked = view.dock.offline
                                for g in t.groups:
                                    if t.sheet:
                                        with a.div(klass="section"):
                                            _group(a, g, view, images, locked, sheet=True)
                                    else:
                                        _group(a, g, view, images, locked)
                        _savebar(a, writable, status, discard=True)
                    for store in view.sizes:
                        a.form(method="post", action=f"config/import/{store}",
                               enctype="multipart/form-data", id=f"import-{store}")
                    if view.dock is not None:
                        with a.form(method="post", action="config", id="recalibrate-form"):
                            a.input(type="hidden", name="mode", value="recalibrate")
                with a.form(method="post", action="config", id="yaml-form",
                            **{"data-title": "Save and restart?",
                               "data-confirm": "Save and restart"}):
                    a.input(type="hidden", name="mode", value="yaml")
                    a.input(type="hidden", name="tab", value=YAML_TAB)
                    with a.section(klass="panel", id=f"panel-{YAML_TAB}", role="tabpanel",
                                   **{"data-tab": YAML_TAB, "aria-labelledby": f"tab-{YAML_TAB}"}):
                        a.textarea(name="text", rows="24", spellcheck="false", _t=view.text,
                                   **{"aria-label": "config.yaml", "data-key": "text",
                                      "data-initial": view.file_text})
                        _savebar(a, writable, status, discard=True)
            with a.dialog(id="review", **{"aria-labelledby": "review-title"}):
                with a.form(method="dialog"):
                    a.h2(klass="label", id="review-title", _t="Save and restart?")
                    a.p(klass="lead", id="review-lead")
                    with a.div(klass="changes-box"):
                        with a.table(klass="changes"):
                            a.tbody(id="review-list", _t="")
                    with a.div(klass="choice"):
                        a.button(value="cancel", _t="Cancel")
                        a.button(value="confirm", klass="primary", id="review-confirm",
                                 _t="Save and restart")
            if view.note in NOTICES:
                title, lead, offers_save = NOTICES[view.note]
                with a.dialog(id="notice", **{"aria-labelledby": "notice-title"}):
                    with a.form(method="dialog"):
                        a.h2(klass="label", id="notice-title", _t=title)
                        a.p(klass="lead", _t=lead)
                        with a.div(klass="choice"):
                            a.button(value="close", autofocus="autofocus", _t="Close",
                                     **({} if offers_save else {"klass": "primary"}))
                            if offers_save:
                                a.button(value="save", klass="primary", _t="Save and restart",
                                         **({} if writable else {"disabled": "disabled"}))
            with a.datalist(id="zones"):
                for zone in sorted(zoneinfo.available_timezones()):
                    a.option(value=zone)
            a.script(src="rough.iife.min.js")
            a.script(src="config.js")
            a.script(src="timepick.js")
            a.script(src="sheet.js")
            a.script(src="ago.js")
    return str(a)


def restarting_html(pages: list[EnvPage], tab: str) -> str:
    """The page a save without config.js gets: it opens the config page
    again after a minute, once the server is back."""
    a = Html()
    a("<!DOCTYPE html>")
    with a.html(lang="en"):
        page_head(a, "Canary · Restarting", refresh=f"60; url=config?saved=1#{tab}")
        with a.body(klass="web config"):
            menu_bar(a, pages, BROWSE_HREF, "config")
            with a.main(klass="settings"):
                a.h1(klass="title label", _t="Config")
                a.p(klass="banner", id="restarting", _t="Restarting…")
    return str(a)


def config_blueprint(pages: list[EnvPage], path: str, check: Callable[[str], None],
                     restart: Callable[[], None],
                     stores: dict[str, Transfer] | None = None,
                     dock: ds.BoardSettings | None = None,
                     boards: Callable[[str], dict | None] | None = None) -> Blueprint:
    """The /web/config routes for the file at ``path``.

    Args:
        check: raises ValueError, with the problem, unless the text would
            start the server.
        restart: restarts the server once the response has gone out.
        stores: the store behind each group of the Storage tab that a file
            can come out of and go into, by the group's ``store`` name.
        dock: the dock's settings, for what the Dock tab says of them and
            for its recalibration.
        boards: what the server knows of a board, as DeviceReports.device
            gives it, for the size the head reports.
    """
    bp = Blueprint("config", __name__, url_prefix="/web/config")
    stores = stores or {}

    @bp.record_once
    def cap_uploads(state):
        state.app.config.setdefault("MAX_CONTENT_LENGTH", MAX_UPLOAD)

    def writable() -> bool:
        return os.access(path, os.W_OK)

    def bak() -> datetime | None:
        try:
            return datetime.fromtimestamp(os.path.getmtime(path + ".bak"))
        except OSError:
            return None

    def page(view: View, status: int = 200):
        view.sizes = {name: store.size() for name, store in stores.items()}
        if dock is not None and view.dock is None:
            view.dock = dock_state(dock)
        if boards is not None:
            view.head = head_panel(boards("canary-head"))
        return config_html(pages, view, writable(), bak()), status

    @bp.route("/live", methods=["GET"])
    def live():
        """The Dock tab's lines about the dock as they are now, for config.js."""
        if dock is None:
            abort(404)
        state = dock_state(dock)
        a = Html()
        _settings_line(a, state)
        return jsonify(state=str(a), recalibration=_recalibration_words(state),
                       offline=state.offline)

    @bp.route("/export/<name>", methods=["GET"])
    def export(name: str):
        store = stores.get(name)
        if store is None:
            abort(404)
        stamp = datetime.now().strftime("%Y%m%d")
        return Response(store.lines(), mimetype="application/x-ndjson", headers={
            "Content-Disposition": f'attachment; filename="{name}-{stamp}.jsonl"'})

    @bp.route("/import/<name>", methods=["POST"])
    def bring_in(name: str):
        store = stores.get(name)
        if store is None:
            abort(404)
        as_json = "application/json" in request.headers.get("Accept", "")

        def answer(words: str, status: int = 200, bad: bool = False, advice: str = "",
                   **counts):
            """The answer as JSON, or the page with it under the import row.
            ``advice`` is for the page alone: with config.js a dialog asks."""
            if as_json:
                return jsonify(words=words, bad=bad, **counts), status
            with open(path) as f:
                view = file_view(f.read())
            view.tab = "storage"
            view.report = Report(name, " ".join(filter(None, (words, advice))), bad)
            return page(view, status)

        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return answer("Choose a file to import.", 400, bad=True)
        try:
            counts = store.take(upload.stream, request.form.get("replace") == "true")
        except Corrupt as exc:
            return answer(f"The file is corrupted and cannot be imported. Line {exc.line}.",
                          400, bad=True)
        except Overlap as exc:
            return answer(f"{exc.held:,} of {exc.total:,} records already exist.",
                          409, bad=True, held=exc.held, total=exc.total,
                          advice="Tick Replace and choose the file again.")
        except FileNotFoundError:
            return answer("This server does not keep those records.", 404, bad=True)
        size = store.size()
        words = f"Added {counts['added']:,} of {counts['total']:,} records."
        if counts["held"]:
            words += f" {counts['held']:,} replaced."
        return answer(words, size=size, shown=_size(size), **counts)

    @bp.errorhandler(413)
    def too_big(exc):
        words = f"The file is too big. The limit is {MAX_UPLOAD // (1024 * 1024)} MB."
        if "application/json" in request.headers.get("Accept", ""):
            return jsonify(words=words, bad=True), 413
        with open(path) as f:
            view = file_view(f.read())
        view.tab = "storage"
        view.report = Report((request.view_args or {}).get("name", ""), words, True)
        return page(view, 413)

    @bp.route("", methods=["GET"])
    def show():
        with open(path) as f:
            view = file_view(f.read())
        if request.args.get("saved"):
            view.status = "Saved."
        return page(view)

    @bp.route("", methods=["POST"])
    def change():
        form = request.form
        mode = form.get("mode") or ("yaml" if "text" in form else "form")
        action = form.get("action", "check")
        with open(path) as f:
            current = f.read()
        view = file_view(current)
        view.tab = form.get("tab", "") if form.get("tab") in TAB_NAMES else ""

        wants_json = action == "review" or "application/json" in request.headers.get("Accept", "")

        def refuse(problem: str, status: int = 400):
            if wants_json:
                return jsonify(problem=problem), status
            view.problem = problem
            return page(view, status)

        if mode == "recalibrate":
            if dock is None:
                abort(404)
            ppm = form.get("ppm", "")
            try:
                dock.recalibrate(ppm)
            except ValueError as exc:
                view.tab = "dock"
                view.dock = dock_state(dock)
                view.dock.ppm = ppm
                view.report = Report("recalibrate", str(exc), True)
                return page(view, 400)
            return redirect("config#dock", 303)

        if mode == "restore":
            try:
                with open(path + ".bak") as f:
                    text = f.read()
            except OSError:
                return refuse("No earlier version.", 404)
        elif mode == "yaml":
            # A text box sends its lines with CRLF.
            text = form.get("text", "").replace("\r\n", "\n")
            view.text, view.tab = text, YAML_TAB
        else:
            view.values.update(cf.submitted(form))
            try:
                edit = cf.apply(current, form)
            except cf.FormError as exc:
                return refuse(str(exc))
            if edit.errors:
                view.errors = edit.errors
                key = next(f.key for f in cf.FIELDS if f.key in edit.errors)
                view.tab = cf.TAB_OF[key]
                return refuse(f"{cf.name_of(cf.BY_KEY[key].path)}: {edit.errors[key]}")
            text = edit.text

        try:
            check(text)
        except ValueError as exc:
            problem = str(exc)
            if mode == "form":
                key, tab = cf.locate(problem)
                if key:
                    view.errors[key] = problem
                view.tab = tab or view.tab
            return refuse(problem)

        if action == "review":
            return jsonify(changes=cf.changes(cf.read(current), cf.read(text)),
                           same=text == current)
        if action != "save":
            view.note = "No problems found."
            return page(view)
        if text == current:
            if wants_json:
                return jsonify(saved=False, same=True)
            view.note = "Nothing to save."
            return page(view)
        if not writable():
            return refuse(READ_ONLY, 403)
        try:
            save(path, text)
        except OSError as exc:
            return refuse(f"Cannot save config.yaml. {exc.strerror}.", 500)
        restart()
        if wants_json:
            return jsonify(saved=True)
        return restarting_html(pages, view.tab or cf.TABS[0].name)

    return bp
