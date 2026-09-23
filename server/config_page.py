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
                         then action=check: whether that would start the server
                              action=review: the same, and what it changes, as JSON
                              action=save: the same check, then the old file kept
                              as config.yaml.bak, the new one written, and the
                              server restarted on it

Nothing guards these routes yet: anyone who can reach the server can change
its config.
"""
from __future__ import annotations

import html
import os
import shutil
import zoneinfo
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from airium import Airium
from flask import Blueprint, Response, abort, jsonify, request

import config_form as cf
from pages.base import EnvPage
from transfer import Corrupt, Overlap, Transfer
from web import menu_bar, page_head

# The most an imported file may weigh.
MAX_UPLOAD = 64 * 1024 * 1024
# The browse page's URL from /web/config, once the server answers again.
BROWSE_HREF = "./"
YAML_TAB = "yaml"
TAB_NAMES = [t.name for t in cf.TABS] + [YAML_TAB]

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


def file_view(text: str) -> View:
    try:
        cfg = cf.read(text)
    except cf.FormError as exc:
        values = cf.shown({})
        return View(text, text, values, dict(values), tab=YAML_TAB,
                    unreadable=str(exc))
    values = cf.shown(cfg)
    return View(text, text, values, dict(values), cf.defaults(cfg))


def esc(value: Any) -> str:
    """``value`` as HTML text or as an attribute's value. Airium writes text
    as given and escapes only the quotes in an attribute."""
    return html.escape(str(value), quote=False)


def _id(key: str) -> str:
    return "f-" + key.replace(".", "-")


def _when(t: datetime) -> str:
    return f"{t:%a} {t.day} {t:%b}, {t:%H:%M}"


def _pool_names(view: View) -> list[str]:
    return [n for n, _ in view.values.get("display.pools", []) if n.strip()]


def _pool_row(a: Airium, key: str, name: str, pages: str, images: list[str]) -> None:
    with a.div(klass="row"):
        a.input(type="text", klass="pool-name", name=key + ".name", value=esc(name),
                placeholder="name", spellcheck="false", autocomplete="off",
                **{"aria-label": "Pool name"})
        a.input(type="text", klass="chips", name=key + ".pages", value=esc(pages),
                spellcheck="false", autocomplete="off", placeholder="breathe.png, co2-trace.png",
                **{"aria-label": "Images", "data-options": esc(" ".join(images))})
        a.button(type="button", klass="remove", _t=esc("×"), **{"aria-label": "Remove this pool"})


def _time_row(a: Airium, key: str, at: str, pool: str, names: list[str]) -> None:
    with a.div(klass="row"):
        a.input(type="time", step="1", name=key + ".at", value=esc(at),
                **{"aria-label": "Wake time"})
        with a.select(name=key + ".pool", **{"aria-label": "Pool"}):
            for n in names + ([pool] if pool and pool not in names else []):
                a.option(value=esc(n), _t=esc(n), **({"selected": "selected"} if n == pool else {}))
        a.button(type="button", klass="remove", _t=esc("×"), **{"aria-label": "Remove this time"})


def _rows(a: Airium, f: cf.Field, view: View, images: list[str], heading: str) -> None:
    rows = view.values.get(f.key, [])
    names = _pool_names(view)
    kind = "pools" if f.kind == "pools" else "times"
    with a.fieldset(klass=f"rows {kind}", id=_id(f.key),
                    **{"data-key": f.key, "data-initial": esc(cf.initial(view.initial[f.key]))}):
        a.legend(klass="name hide" if f.label == heading else "name", _t=esc(f.label))
        a.input(type="hidden", name=f.key, value="1")
        with a.div(klass="list"):
            for first, second in rows:
                if kind == "pools":
                    _pool_row(a, f.key, first, second, images)
                else:
                    _time_row(a, f.key, first, second, names)
        with a.template():
            if kind == "pools":
                _pool_row(a, f.key, "", "", images)
            else:
                _time_row(a, f.key, "", "", names)
        with a.div(klass="foot"):
            a.button(type="button", klass="add",
                     _t=esc("Add a pool" if kind == "pools" else "Add a time"))
            if f.help:
                a.p(klass="help", _t=esc(f.help))


def _control(a: Airium, f: cf.Field, view: View, env: str | None) -> None:
    value = view.values.get(f.key, "")
    lock = {"disabled": "disabled"} if env is not None else {}
    marks = {"data-default": esc(view.defaults[f.key])} if f.key in view.defaults else {}
    own = {"id": _id(f.key), "name": f.key, "data-key": f.key,
           "data-initial": esc(cf.initial(view.initial.get(f.key, ""))), **lock, **marks}
    with a.div(klass="control"):
        if f.kind == "choice":
            chosen = env if env is not None else value
            with a.div(klass="segments", role="radiogroup", id=_id(f.key),
                       **{"aria-labelledby": _id(f.key) + "-name", "data-key": f.key,
                          "data-initial": esc(view.initial.get(f.key, ""))}, **marks):
                for choice, words in f.choices:
                    with a.label():
                        a.input(type="radio", name=f.key, value=choice, **lock,
                                **({"checked": "checked"} if choice == chosen else {}))
                        a.span(_t=esc(words))
        elif f.kind in ("bool", "quiet"):
            on = (env or "").strip().lower() in ("1", "true", "yes", "on") if env is not None \
                else value == "true"
            a.input(type="hidden", name=f.key, value="false", **lock)
            a.input(type="checkbox", klass="switch", value="true", **own,
                    **({"checked": "checked"} if on else {}))
            a.span(klass="state", **{"aria-hidden": "true"})
        else:
            attrs: dict[str, Any] = {"value": esc(env if env is not None else value)}
            if f.hint:
                attrs["placeholder"] = f.hint
            if f.kind in ("int", "number"):
                attrs.update(type="number", step=str(f.step) if f.kind == "int" else "any",
                             inputmode="numeric" if f.kind == "int" else "decimal")
                if f.minimum is not None:
                    attrs["min"] = f"{f.minimum:g}"
                if f.maximum is not None:
                    attrs["max"] = f"{f.maximum:g}"
            elif f.kind == "time":
                attrs.update(type="time")
            else:
                attrs.update(type="text", spellcheck="false", autocomplete="off")
                if f.kind == "zone":
                    attrs["list"] = "zones"
                if f.kind == "order":
                    attrs.update(klass="chips",
                                 **{"data-options": esc(" ".join(_pool_names(view))),
                                    "data-options-from": "display.pools"})
            a.input(**own, **attrs)
            if f.unit:
                a.span(klass="unit", _t=esc(f.unit))


def _reset_button(a: Airium, f: cf.Field, view: View) -> None:
    """Puts the default back; it shows once the value differs from it."""
    at_default = view.values.get(f.key) == view.defaults[f.key]
    a.button(type="button", klass="reset", _t=esc("Reset"),
             **{"aria-label": esc(f"Reset {f.label}")}, **({"hidden": "hidden"} if at_default else {}))


def _field(a: Airium, f: cf.Field, view: View, images: list[str], heading: str) -> None:
    env = f.env_value()
    error = view.errors.get(f.key)
    klass = "field"
    if f.kind in ("pools", "times"):
        klass += " wide"
    if error:
        klass += " invalid"
    with a.div(klass=klass, **{"data-field": f.key}, **({"data-when": f.when} if f.when else {})):
        if f.kind in ("pools", "times"):
            _rows(a, f, view, images, heading)
        else:
            with a.div(klass="head"):
                if f.kind == "choice":
                    a.span(klass="name", id=_id(f.key) + "-name", _t=esc(f.label))
                else:
                    a.label(klass="name", for_=_id(f.key), _t=esc(f.label))
                if f.key in view.defaults and env is None:
                    _reset_button(a, f, view)
            _control(a, f, view, env)
        if f.help and f.kind not in ("pools", "times"):
            a.p(klass="help", _t=esc(f.help))
        if env is not None:
            a.p(klass="env", _t=esc(f"Set by {f.env_name}"))
        if error:
            a.p(klass="error", id="e-" + _id(f.key)[2:], _t=esc(error))


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
            a.span(klass="name", _t=esc("Export"))
        with a.div(klass="control"):
            a.a(klass="button" if size else "button off", _t=esc("Download"),
                **({"href": f"config/export/{store}", "download": "download"} if size
                   else {"aria-disabled": "true"}))
            a.span(klass="unit", _t=esc(_size(size) if size else "No records yet."))


def _import(a: Airium, store: str, report: Report) -> None:
    """The row that takes a file back in. Its controls belong to the form
    beside the settings form, because a form cannot hold another."""
    form = f"import-{store}"
    with a.div(klass="field", **{"data-import": store}):
        with a.div(klass="head"):
            a.label(klass="name", for_=f"file-{store}", _t=esc("Import"))
        with a.div(klass="control"):
            a.input(type="file", id=f"file-{store}", name="file", form=form,
                    accept=".jsonl,application/x-ndjson")
            with a.label(klass="over"):
                a.input(type="checkbox", name="replace", value="true", form=form)
                a.span(_t=esc("Replace"))
            a.button(type="submit", klass="button", form=form, _t=esc("Upload"))
        if report.store == store:
            a.p(klass="error" if report.bad else "help", _t=esc(report.words))


def _savebar(a: Airium, writable: bool, status: str, *, discard: bool) -> None:
    with a.footer(klass="savebar"):
        a.p(klass="status", _t=esc(status), **{"aria-live": "polite",
                                          "data-idle": "No changes."})
        with a.div(klass="choice"):
            if discard:
                a.a(klass="button discard", href="config", _t=esc("Discard"))
            a.button(type="submit", name="action", value="check", _t=esc("Check"))
            a.button(type="submit", name="action", value="save", klass="primary",
                     _t=esc("Save and restart"), **({} if writable else {"disabled": "disabled"}))


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
    a = Airium()
    a("<!DOCTYPE html>")
    with a.html(lang="en"):
        page_head(a, "Canary · Config")
        with a.body(klass="web config"):
            menu_bar(a, pages, BROWSE_HREF, "config")
            with a.main(klass="settings"):
                with a.div(klass="top"):
                    a.h1(klass="title label", _t=esc("Config"))
                    with a.div(klass="where"):
                        if bak is not None and writable:
                            with a.form(method="post", action="config", klass="restore",
                                        id="restore-form",
                                        **{"data-title": "Restore the previous version?",
                                           "data-confirm": "Restore and restart"}):
                                a.input(type="hidden", name="mode", value="restore")
                                a.span(klass="stamp", _t=esc(f"Last saved {_when(bak)}"))
                                a.button(type="submit", name="action", value="save",
                                         klass="link", _t=esc("Restore"))
                with a.nav(klass="tabs", role="tablist", **{"aria-label": "Sections"},
                           **({"data-open": view.tab} if view.tab else {})):
                    for name, title in tabs:
                        a.a(href=f"#{name}", id=f"tab-{name}", role="tab",
                            klass="tab problem" if name in marked else "tab",
                            _t=esc(title), **{"data-tab": name, "aria-controls": f"panel-{name}"})
                if not writable:
                    a.p(klass="banner", id="read-only",
                        _t=esc(READ_ONLY))
                if view.unreadable:
                    a.p(klass="banner problem", id="unreadable", _t=esc(view.unreadable))
                if view.problem:
                    a.p(klass="banner problem", id="problem", _t=esc(f"Not saved: {view.problem}"))
                if view.note:
                    a.p(klass="banner", id="note", _t=esc(view.note))
                if not view.unreadable:
                    with a.form(method="post", action="config", id="settings-form",
                                novalidate="novalidate",
                                **{"data-title": "Save and restart?",
                                   "data-confirm": "Save and restart"}):
                        a.input(type="hidden", name="mode", value="form")
                        a.input(type="hidden", name="tab", value=view.tab or cf.TABS[0].name)
                        for t in cf.TABS:
                            with a.section(klass="panel", id=f"panel-{t.name}", role="tabpanel",
                                           **{"data-tab": t.name,
                                              "aria-labelledby": f"tab-{t.name}"}):
                                for g in t.groups:
                                    if g.heading:
                                        a.h2(klass="group label", _t=esc(g.heading))
                                    with a.div(klass="fields"):
                                        for f in g.fields:
                                            _field(a, f, view, images, g.heading)
                                        if g.store in view.sizes:
                                            _export(a, g.store, view.sizes[g.store])
                                            _import(a, g.store, view.report)
                        _savebar(a, writable, status, discard=True)
                    for store in view.sizes:
                        a.form(method="post", action=f"config/import/{store}",
                               enctype="multipart/form-data", id=f"import-{store}")
                with a.form(method="post", action="config", id="yaml-form",
                            **{"data-title": "Save and restart?",
                               "data-confirm": "Save and restart"}):
                    a.input(type="hidden", name="mode", value="yaml")
                    a.input(type="hidden", name="tab", value=YAML_TAB)
                    with a.section(klass="panel", id=f"panel-{YAML_TAB}", role="tabpanel",
                                   **{"data-tab": YAML_TAB, "aria-labelledby": f"tab-{YAML_TAB}"}):
                        a.textarea(name="text", rows="24", spellcheck="false", _t=esc(view.text),
                                   **{"aria-label": "config.yaml", "data-key": "text",
                                      "data-initial": esc(view.file_text)})
                        _savebar(a, writable, status, discard=True)
            with a.dialog(id="review", **{"aria-labelledby": "review-title"}):
                with a.form(method="dialog"):
                    a.h2(klass="label", id="review-title", _t=esc("Save and restart?"))
                    a.p(klass="lead", id="review-lead")
                    with a.div(klass="changes-box"):
                        with a.table(klass="changes"):
                            a.tbody(id="review-list", _t=esc(""))
                    with a.div(klass="choice"):
                        a.button(value="cancel", _t=esc("Cancel"))
                        a.button(value="confirm", klass="primary", id="review-confirm",
                                 _t=esc("Save and restart"))
            with a.datalist(id="zones"):
                for zone in sorted(zoneinfo.available_timezones()):
                    a.option(value=zone)
            a.script(src="config.js")
    return str(a)


def restarting_html(pages: list[EnvPage], tab: str) -> str:
    """The page a save without config.js gets: it opens the config page
    again after a minute, once the server is back."""
    a = Airium()
    a("<!DOCTYPE html>")
    with a.html(lang="en"):
        page_head(a, "Canary · Restarting", refresh=f"60; url=config?saved=1#{tab}")
        with a.body(klass="web config"):
            menu_bar(a, pages, BROWSE_HREF, "config")
            with a.main(klass="settings"):
                a.h1(klass="title label", _t=esc("Config"))
                a.p(klass="banner", id="restarting", _t=esc("Restarting…"))
    return str(a)


def config_blueprint(pages: list[EnvPage], path: str, check: Callable[[str], None],
                     restart: Callable[[], None],
                     stores: dict[str, Transfer] | None = None) -> Blueprint:
    """The /web/config routes for the file at ``path``.

    Args:
        check: raises ValueError, with the problem, unless the text would
            start the server.
        restart: restarts the server once the response has gone out.
        stores: the store behind each group of the Storage tab that a file
            can come out of and go into, by the group's ``store`` name.
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
        return config_html(pages, view, writable(), bak()), status

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
