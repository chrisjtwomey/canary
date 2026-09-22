"""The config page's form: its tabs and fields, and what a filled-in form
does to config.yaml.

The file is edited with ruamel.yaml, which keeps its comments and layout, and
read with PyYAML, which is what the server starts on. The two read some plain
scalars differently (``01:00`` is a string to ruamel and a number to PyYAML),
so a string is written in quotes whenever PyYAML would read it as something
else, and every edit is read back with PyYAML before it is accepted.
"""
from __future__ import annotations

import io
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

import yaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import CommentMark
from ruamel.yaml.scalarstring import DoubleQuotedScalarString
from ruamel.yaml.tokens import CommentToken
from ruamel.yaml.util import load_yaml_guess_indent

from schedule import DEFAULT_QUIET

# A key the file does not have.
MISSING: Any = object()

# The display.schedule keys that are not wake times.
SCHEDULE_KEYS = ("type", "reshuffle_hours", "seed", "every", "order")
INTERVAL_KEYS = ("display.schedule.every", "display.schedule.order")


@dataclass(frozen=True)
class Field:
    """One setting on the form.

    ``default`` is what the server takes when the key is absent, or a function
    of the config that gives it; the form shows it as the field's value.
    ``hint`` is an example of the value, for a field with no default. ``when``
    is another field and a
    value, as ``source.kind=store``: the field shows only while that one holds
    it. ``env`` is false for keys the server reads without looking for an
    environment variable.
    """
    key: str
    label: str
    help: str = ""
    kind: str = "text"      # text zone secret int number bool choice time quiet pools order times
    default: Any = None
    hint: str = ""
    choices: tuple[tuple[str, str], ...] = ()
    unit: str = ""
    minimum: float | None = None
    maximum: float | None = None
    step: int = 1
    when: str = ""
    env: bool = True

    @property
    def path(self) -> tuple[str, ...]:
        return tuple(self.key.split("."))

    @property
    def env_name(self) -> str:
        return "_".join(self.path).upper()


    def env_value(self) -> str | None:
        """The environment variable that sets this key over the file, if one is set."""
        return os.environ.get(self.env_name) if self.env else None


@dataclass(frozen=True)
class Group:
    """``store`` names the store this group's file holds, for the export row."""
    heading: str
    fields: tuple[Field, ...]
    store: str = ""


@dataclass(frozen=True)
class Tab:
    name: str
    title: str
    groups: tuple[Group, ...]

    @property
    def fields(self) -> list[Field]:
        return [f for g in self.groups for f in g.fields]


TABS: tuple[Tab, ...] = (
    Tab("server", "Server", (
        Group("", (
            Field("server.port", "Port", "", "int", 8080, minimum=1, maximum=65535),
            Field("server.regen_lead_seconds", "Pre-render pages", "Before each refresh.", "int", 120,
                  unit="seconds", minimum=0),
            Field("debug", "Debug log", "", "bool", False),
        )),
        Group("Location", (
            Field("server.timezone", "Time zone", "", "zone", lambda cfg: host_zone()),
            Field("site.altitude_m", "Altitude", "For sea-level pressure.", "number", 0, unit="m"),
        )),
    )),
    Tab("display", "Display", (
        Group("Pools", (
            Field("display.pools", "Pools", "Drag to reorder.", "pools", env=False),
        )),
        Group("Schedule", (
            Field("display.schedule.type", "Change page", "", "choice",
                  choices=(("interval", "Interval"), ("times", "Set times")),
                  env=False),
            Field("display.schedule.every", "Every", "300 → :00, :05, :10 …", "int",
                  unit="seconds", minimum=1, when="display.schedule.type=interval", env=False),
            Field("display.schedule.order", "Order", "", "order", lambda cfg: pool_names(cfg),
                  when="display.schedule.type=interval", env=False),
            Field("display.schedule.reshuffle_hours", "Reshuffle",
                  "Changes where each pool starts.", "number", 3, unit="hours", minimum=0,
                  env=False),
            Field("display.schedule.seed", "Seed", "", "int", 0, env=False),
            Field("display.schedule.times", "Times", "", "times",
                  when="display.schedule.type=times", env=False),
        )),
    )),
    Tab("image", "Image", (
        Group("Size", (
            Field("image.width", "Width", "", "int", 1280, unit="px",
                  minimum=1),
            Field("image.height", "Height", "", "int", 720, unit="px",
                  minimum=1),
        )),
        Group("Drawn area", (
            Field("image.innerWidth", "Width", "", "int",
                  lambda cfg: effective(cfg, "image.width"), unit="px",
                  minimum=1),
            Field("image.innerHeight", "Height", "", "int",
                  lambda cfg: effective(cfg, "image.height"),
                  unit="px", minimum=1),
            Field("image.innerAlignX", "Across", "", "choice", "center",
                  choices=(("left", "Left"), ("center", "Centre"), ("right", "Right"))),
            Field("image.innerAlignY", "Up and down", "", "choice", "center",
                  choices=(("top", "Top"), ("center", "Centre"), ("bottom", "Bottom"))),
        )),
    )),
    Tab("boards", "Boards", (
        Group("Sending", (
            Field("posts.every", "Send every", "Whole minutes.", "int", 300, unit="seconds",
                  minimum=60, step=60),
            Field("posts.quiet", "Quiet hours",
                  "A time range of less frequent sensor readings.", "quiet", True, env=False),
            Field("posts.quiet.from", "From", "", "time", when="posts.quiet=true", env=False),
            Field("posts.quiet.to", "To", "", "time", when="posts.quiet=true", env=False),
            Field("posts.quiet.every", "Send every (quiet)", "", "int",
                  lambda cfg: effective(cfg, "posts.every"),
                  unit="seconds", minimum=60, step=60, when="posts.quiet=true", env=False),
        )),
    )),
    Tab("storage", "Storage", (
        Group("Sensor readings", (
            Field("source.path", "File", "", "text", "sensor-readings.db"),
            Field("source.keep_days", "Delete after", "0 = never.", "number", 0, unit="days",
                  minimum=0),
        ), store="sensor-readings"),
        Group("Board reports", (
            Field("status.path", "File", "", "text", "status.db"),
            Field("status.keep_days", "Delete after", "0 = never.", "number", 7, unit="days",
                  minimum=0),
        ), store="board-reports"),
        Group("Calibration", (
            Field("calibration.path", "File", "", "text", "calibration.db"),
            Field("calibration.keep_days", "Delete after", "0 = never.", "number", 3, unit="days",
                  minimum=0),
        ), store="calibration"),
    )),
    Tab("firmware", "Firmware", (
        Group("Updates", (
            Field("client.firmware.enabled", "Update boards", "", "bool", False),
            Field("client.firmware.offer_dev_builds", "Development builds",
                  "For boards not on a released version.", "bool", False),
            Field("client.firmware.dir", "Folder", "", "text", "firmware"),
        )),
        Group("GitHub releases", (
            Field("client.firmware.source.github", "Repository", "Empty: add files by hand.",
                  "text", hint="owner/repo"),
            Field("client.firmware.source.asset", "Asset", "", "text", "firmware.bin"),
            Field("client.firmware.source.poll_seconds", "Check every", "", "int", 3600,
                  unit="seconds", minimum=1),
            Field("client.firmware.source.token", "Token", "Needed for a private repo. "
                  "CLIENT_FIRMWARE_SOURCE_TOKEN sets it too.", "secret"),
        )),
    )),
    Tab("mqtt", "MQTT", (
        Group("", (
            Field("mqtt.enabled", "Board log", "Relay board logs from MQTT.", "bool", False),
            Field("mqtt.host", "Host", "", "text", "localhost"),
            Field("mqtt.port", "Port", "", "int", 1883, minimum=1, maximum=65535),
            Field("mqtt.topic", "Topic", "", "text", "mqtt/epd-client"),
        )),
    )),
)

FIELDS: tuple[Field, ...] = tuple(f for t in TABS for f in t.fields)
BY_KEY: dict[str, Field] = {f.key: f for f in FIELDS}
TAB_OF: dict[str, str] = {f.key: t.name for t in TABS for f in t.fields}


class FieldError(ValueError):
    """A value the form cannot write. The message is for the person filling it in."""


class FormError(ValueError):
    """The form cannot make this edit at all. The message says to use the YAML tab."""


# ── Reading ─────────────────────────────────────────────────────────

def read(text: str) -> dict:
    """``text`` as the server reads it.

    Raises:
        FormError: it is not YAML, or not a mapping.
    """
    try:
        cfg = yaml.safe_load(text)
    except yaml.YAMLError:
        raise FormError("Not valid YAML. Fix it in the YAML tab.")
    if cfg is None:
        return {}
    if not isinstance(cfg, dict):
        raise FormError("Top level is not a mapping. Fix it in the YAML tab.")
    return cfg


def lookup(cfg: Any, path: Iterable) -> Any:
    node = cfg
    for k in path:
        if not isinstance(node, dict) or k not in node:
            return MISSING
        node = node[k]
    return node


def time_rows(cfg: dict) -> list[tuple[str, str]]:
    """The schedule's wake times and the pool at each."""
    sched = lookup(cfg, ("display", "schedule"))
    if not isinstance(sched, dict):
        return []
    return [(str(t), str(n)) for t, n in sched.items() if t not in SCHEDULE_KEYS]


def host_zone() -> str:
    """The zone the server runs in when config.yaml names none."""
    tz = datetime.now().astimezone().tzinfo
    return str(getattr(tz, "key", "") or (tz.tzname(None) if tz else "") or "UTC")


def pool_names(cfg: dict) -> list[str]:
    pools = lookup(cfg, ("display", "pools"))
    return [str(n) for n in pools] if isinstance(pools, dict) else []


def default_of(f: Field, cfg: dict) -> Any:
    """What the server takes for ``f`` when config.yaml leaves it out."""
    return f.default(cfg) if callable(f.default) else f.default


def effective(cfg: dict, key: str) -> Any:
    """The value the server uses for ``key``: the file's, or the default."""
    v = lookup(cfg, BY_KEY[key].path)
    return default_of(BY_KEY[key], cfg) if v is MISSING else v


def _as_input(value: Any) -> str:
    if value is None or value is MISSING:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(map(str, value))
    return str(value)


def _pool_rows(v: Any) -> list[tuple[str, str]]:
    if not isinstance(v, dict):
        return []
    return [(str(n), ", ".join(map(str, p if isinstance(p, list) else [p]))) for n, p in v.items()]


def _quiet_block(cfg: dict) -> dict | None:
    """posts.quiet when the file gives one; None when the defaults apply or it is off."""
    q = lookup(cfg, ("posts", "quiet"))
    return q if isinstance(q, dict) and q else None


def shown(cfg: dict) -> dict[str, Any]:
    """Each field's value as its input shows it: a string, or rows for the
    pools and the wake times."""
    out: dict[str, Any] = {}
    quiet = _quiet_block(cfg)
    for f in FIELDS:
        v = lookup(cfg, f.path)
        if f.kind == "pools":
            out[f.key] = _pool_rows(v)
        elif f.kind == "times":
            out[f.key] = time_rows(cfg)
        elif f.kind == "quiet":
            out[f.key] = "false" if v is not MISSING and not v else "true"
        elif f.key.startswith("posts.quiet.") and quiet is None:
            out[f.key] = str(DEFAULT_QUIET[f.path[-1]])
        elif f.kind == "secret":
            out[f.key] = ""
        else:
            out[f.key] = _as_input(default_of(f, cfg) if v is MISSING else v)
    return out


def defaults(cfg: dict) -> dict[str, str]:
    """Each field's default as its input shows it, for the fields that have one."""
    quiet = _quiet_block(cfg)
    out: dict[str, str] = {}
    for f in FIELDS:
        if f.kind in ("pools", "times", "secret"):
            continue
        if f.key.startswith("posts.quiet.") and quiet is None:
            d: Any = DEFAULT_QUIET[f.path[-1]]
        else:
            d = default_of(f, cfg)
        if d is not None:
            out[f.key] = _as_input(d)
    return out



def submitted(form) -> dict[str, Any]:
    """The values a posted form holds, as :func:`shown` gives them."""
    out: dict[str, Any] = {}
    for f in FIELDS:
        if f.key not in form or f.kind == "secret":
            continue
        if f.kind == "pools":
            out[f.key] = list(zip(form.getlist(f.key + ".name"), form.getlist(f.key + ".pages")))
        elif f.kind == "times":
            out[f.key] = list(zip(form.getlist(f.key + ".at"), form.getlist(f.key + ".pool")))
        else:
            out[f.key] = form.getlist(f.key)[-1]
    return out


def initial(value: Any) -> str:
    """A value as config.js compares it, to tell whether the field has changed."""
    if isinstance(value, list):
        return json.dumps([list(r) for r in value], separators=(",", ":"), ensure_ascii=False)
    return value


def has_secret(cfg: dict, f: Field) -> bool:
    return bool(lookup(cfg, f.path) not in (MISSING, None, ""))


# ── Parsing ─────────────────────────────────────────────────────────

_HHMM = re.compile(r"(\d{1,2}):(\d{2})")
_HHMMSS = re.compile(r"(\d{1,2}):(\d{2})(?::(\d{2}))?")


def _bounds(f: Field, v: float) -> None:
    if f.minimum is not None and v < f.minimum:
        raise FieldError(f"Must be at least {f.minimum:g}.")
    if f.maximum is not None and v > f.maximum:
        raise FieldError(f"Must be at most {f.maximum:g}.")
    if f.step > 1 and v % f.step:
        raise FieldError(f"Must be a multiple of {f.step}.")


def _images(pages: str) -> list[str]:
    return [p.strip() for p in pages.split(",") if p.strip()]


def _parse_pools(rows) -> dict[str, list[str]]:
    pools: dict[str, list[str]] = {}
    for name, pages in rows:
        name, images = name.strip(), _images(pages)
        if not name and not images:
            continue
        if not name:
            raise FieldError("Each pool needs a name.")
        if name in pools:
            raise FieldError(f"Duplicate pool: {name}.")
        if not images:
            raise FieldError(f"{name} has no images.")
        pools[name] = images
    return pools


def _parse_times(rows) -> list[tuple[str, str]]:
    out: dict[str, str] = {}
    for at, pool in rows:
        at, pool = at.strip(), pool.strip()
        if not at and not pool:
            continue
        if not at:
            raise FieldError(f"{pool} has no time.")
        m = _HHMMSS.fullmatch(at)
        if not m or int(m[1]) > 23 or int(m[2]) > 59 or int(m[3] or 0) > 59:
            raise FieldError(f"{at}: not a time.")
        at = f"{int(m[1]):02d}:{m[2]}:{m[3] or '00'}"
        if not pool:
            raise FieldError(f"{at}: no pool.")
        if at in out:
            raise FieldError(f"Duplicate time: {at}.")
        out[at] = pool
    return list(out.items())


def parse(f: Field, raw: Any) -> Any:
    """The value to write for what the input holds; None takes the key out,
    so the server uses its default."""
    if f.kind == "pools":
        return _parse_pools(raw)
    if f.kind == "times":
        return _parse_times(raw)
    raw = str(raw).strip()
    if f.kind in ("bool", "quiet"):
        return raw == "true"
    if raw == "":
        return None
    if f.kind == "int":
        try:
            v = int(raw)
        except ValueError:
            raise FieldError("Must be a whole number.") from None
        _bounds(f, v)
        return v
    if f.kind == "number":
        try:
            v = int(raw)
        except ValueError:
            try:
                v = float(raw)
            except ValueError:
                raise FieldError("Must be a number.") from None
            if not math.isfinite(v):
                raise FieldError("Must be a number.")
        _bounds(f, v)
        return v
    if f.kind == "choice":
        if raw not in [c for c, _ in f.choices]:
            raise FieldError("Must be one of " + ", ".join(w for _, w in f.choices) + ".")
        return raw
    if f.kind == "time":
        m = _HHMM.fullmatch(raw)
        if not m or int(m[1]) > 23 or int(m[2]) > 59:
            raise FieldError("Must be HH:MM.")
        return f"{int(m[1]):02d}:{m[2]}"
    if f.kind == "order":
        return _images(raw)
    return raw


def _same(a: Any, b: Any) -> bool:
    """Whether the file's value ``a`` already says ``b``: a number is not the
    string of its digits, nor is true 1."""
    if a is MISSING:
        return False
    return (isinstance(a, bool) == isinstance(b, bool) and isinstance(a, str) == isinstance(b, str)
            and a == b)


# ── Writing ─────────────────────────────────────────────────────────

def _plain(s: str) -> bool:
    """Whether PyYAML reads ``s``, unquoted, as the same string. A time of
    day is quoted anyway: 1:00 unquoted is a number of minutes."""
    if _HHMMSS.fullmatch(s):
        return False
    try:
        return yaml.safe_load(s) == s
    except yaml.YAMLError:
        return False


def _node(value: Any) -> Any:
    """``value`` as ruamel writes it: strings quoted when they must be, lists
    on one line, mappings as blocks."""
    if isinstance(value, str):
        return value if _plain(value) else DoubleQuotedScalarString(value)
    if isinstance(value, list):
        seq = CommentedSeq(_node(v) for v in value)
        seq.fa.set_flow_style()
        return seq
    if isinstance(value, dict):
        m = CommentedMap((_node(k), _node(v)) for k, v in value.items())
        if not value:
            m.fa.set_flow_style()
        return m
    return value


def _is_block(v: Any) -> bool:
    return isinstance(v, CommentedMap) and len(v) > 0 and not v.fa.flow_style()


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


# ruamel keeps the comment after a key as one token: the rest of the key's
# line, then every line up to the next key. A key with a block mapping under
# it has its token on its own line, and the lines after the block hang off
# the block's last key. These helpers move those lines when a key comes or
# goes, so a comment stays beside what it describes.

def _end(m: CommentedMap, key: Any) -> tuple[CommentedMap, Any]:
    """The mapping and key whose token holds the lines after ``m[key]`` and all under it."""
    while _is_block(m[key]):
        m = m[key]
        key = next(reversed(m))
    return m, key


def _after(m: CommentedMap, key: Any) -> str:
    item = m.ca.items.get(key)
    tok = item[2] if item and len(item) > 2 else None
    return tok.value.partition("\n")[2] if tok is not None else ""


def _set_after(m: CommentedMap, key: Any, lines: str) -> None:
    item = m.ca.items.get(key)
    tok = item[2] if item and len(item) > 2 else None
    if tok is not None:
        tok.value = tok.value.partition("\n")[0] + "\n" + lines
    elif lines:
        m.ca.items.setdefault(key, [None, None, None, None])[2] = CommentToken(
            "\n" + lines, CommentMark(0), None)


def _split(lines: str, indent: int) -> tuple[str, str]:
    """``lines`` in two at the first blank line or the first one indented
    less than ``indent``: what belongs with the entry, and what comes after
    the mapping it is in."""
    parts = lines.splitlines(keepends=True)
    for i, line in enumerate(parts):
        if not line.strip() or _indent_of(line) < indent:
            return "".join(parts[:i]), "".join(parts[i:])
    return lines, ""


def _outside(lines: str, indent: int) -> str:
    """The lines that outlive an entry at ``indent``: blanks, and comments no deeper than it."""
    return "".join(ln for ln in lines.splitlines(keepends=True)
                   if not ln.strip() or _indent_of(ln) <= indent)


def _join(a: str, b: str) -> str:
    """``a`` then ``b``, without adding to the blank lines where they meet."""
    head, tail = a.splitlines(keepends=True), b.splitlines(keepends=True)
    while head and tail and not head[-1].strip() and not tail[0].strip():
        tail.pop(0)
    return "".join(head + tail)


def _yaml(indent: int = 2, offset: int = 0) -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=indent, sequence=indent + offset, offset=offset)
    return y


class Doc:
    """config.yaml as ruamel holds it, with edits that keep its comments."""

    def __init__(self, text: str):
        if text.strip():
            try:
                root, ind, offset = load_yaml_guess_indent(text)
            except Exception:  # noqa: BLE001 - any ruamel failure means the form cannot edit it
                raise FormError("Not valid YAML. Fix it in the YAML tab.") from None
            self.ind = ind or 2
            self.offset = offset or 0
            # load_yaml_guess_indent loads without preserve_quotes.
            root = _yaml(self.ind, self.offset).load(text)
        else:
            root, self.ind, self.offset = None, 2, 0
        if root is None:
            root = CommentedMap()
        if not isinstance(root, CommentedMap):
            raise FormError("Top level is not a mapping. Fix it in the YAML tab.")
        self.root = root

    def text(self) -> str:
        out = io.StringIO()
        _yaml(self.ind, self.offset).dump(self.root, out)
        return out.getvalue()

    def _chain(self, path) -> list[tuple[CommentedMap, int]]:
        """The mappings along ``path``'s parents with their depths, as far as they go."""
        chain = [(self.root, 0)]
        for depth, k in enumerate(path[:-1], start=1):
            v = chain[-1][0].get(k)
            if not isinstance(v, CommentedMap):
                break
            chain.append((v, depth))
        return chain

    def get(self, path) -> Any:
        return lookup(self.root, path)

    def set(self, path, value: Any) -> None:
        node = _node(value)
        m, depth = self.root, 0
        unflowed = None
        for i, k in enumerate(path[:-1]):
            v = m.get(k)
            if isinstance(v, CommentedMap):
                if v.fa.flow_style():
                    # {} becoming a block: the lines after its key go after the block.
                    unflowed = (m, k, _after(m, k))
                    _set_after(m, k, "")
                    v.fa.set_block_style()
                m, depth = v, depth + 1
                continue
            for j in reversed(path[i + 1:]):
                node = CommentedMap([(_node(j), node)])
            path = path[:i + 1]
            break
        key = path[-1]
        if key in m:
            self._replace(m, depth, key, node)
        else:
            self._append(m, depth, _node(key), node)
        if unflowed:
            um, uk, lines = unflowed
            em, ek = _end(um, uk)
            _set_after(em, ek, _after(em, ek) + lines)

    def _append(self, m: CommentedMap, depth: int, key: Any, node: Any) -> None:
        moved = ""
        if len(m):
            em, ek = _end(m, next(reversed(m)))
            keep, moved = _split(_after(em, ek), self.ind * depth)
            if depth == 0:
                keep += "\n"
            _set_after(em, ek, keep)
        m.ca.items.pop(key, None)
        m[key] = node
        if moved:
            em, ek = _end(m, key)
            _set_after(em, ek, _after(em, ek) + moved)

    def _replace(self, m: CommentedMap, depth: int, key: Any, node: Any) -> None:
        if not _is_block(m[key]) and not _is_block(node):
            m[key] = node
            return
        em, ek = _end(m, key)
        lines = _after(em, ek)
        if _is_block(m[key]):
            lines = _outside(lines, self.ind * depth)
            _set_after(m, key, "")
        _set_after(em, ek, "")
        m[key] = node
        em, ek = _end(m, key)
        _set_after(em, ek, _after(em, ek) + lines)

    def _delete(self, m: CommentedMap, depth: int, key: Any, carried: str = "") -> str:
        """Take ``key`` out of ``m``. The lines after it move to the entry
        before it; with none before it, they are handed back."""
        keys = list(m)
        i = keys.index(key)
        em, ek = _end(m, key)
        own = _after(m, key) if em is not m else ""
        lines = _outside(own + _after(em, ek) + carried, self.ind * depth)
        del m[key]
        m.ca.items.pop(key, None)
        if i > 0 and lines:
            pm, pk = _end(m, keys[i - 1])
            _set_after(pm, pk, _join(_after(pm, pk), lines))
            return ""
        return lines

    def remove(self, path) -> bool:
        """Take the key at ``path`` out, and any mapping that leaves empty."""
        chain = self._chain(path)
        if len(chain) < len(path):
            return False
        m, depth = chain[-1]
        if path[-1] not in m:
            return False
        carried = self._delete(m, depth, path[-1])
        level = len(path) - 1
        while level > 0 and not len(chain[level][0]):
            parent, pdepth = chain[level - 1]
            carried = self._delete(parent, pdepth, path[level - 1], carried)
            level -= 1
        if carried and level > 0:
            parent = chain[level - 1][0]
            _set_after(parent, path[level - 1], _join(_after(parent, path[level - 1]), carried))
        return True

    def set_pools(self, pools: dict[str, list[str]]) -> None:
        pm = self.get(("display", "pools"))
        if not isinstance(pm, CommentedMap) or not len(pm):
            self.set(("display", "pools"), pools)
            return
        if pm.fa.flow_style():
            pm.fa.set_block_style()
        keys = {str(k): k for k in pm}
        for name, images in pools.items():
            if name not in keys:
                self._append(pm, 2, _node(name), _node(images))
                keys[name] = name
            elif isinstance(pm[keys[name]], CommentedSeq):
                if list(pm[keys[name]]) != images:
                    pm[keys[name]][:] = [_node(i) for i in images]
            else:
                self._replace(pm, 2, keys[name], _node(images))
        for name, k in list(keys.items()):
            if name not in pools:
                self.remove(("display", "pools", k))
                del keys[name]
        if [str(k) for k in pm] != list(pools):
            em, ek = _end(pm, next(reversed(pm)))
            keep, moved = _split(_after(em, ek), self.ind * 2)
            _set_after(em, ek, keep)
            for name in pools:
                pm.move_to_end(keys[name])
            em, ek = _end(pm, next(reversed(pm)))
            _set_after(em, ek, _after(em, ek) + moved)

    def set_times(self, rows: list[tuple[str, str]]) -> None:
        wanted = dict(rows)
        for at, pool in rows:
            if self.get(("display", "schedule", at)) != pool:
                self.set(("display", "schedule", at), pool)
        sm = self.get(("display", "schedule"))
        if isinstance(sm, CommentedMap):
            for k in [k for k in sm if k not in SCHEDULE_KEYS and str(k) not in wanted]:
                self.remove(("display", "schedule", k))


# ── Applying a form ─────────────────────────────────────────────────

@dataclass
class Edit:
    """What a posted form does to config.yaml."""
    text: str
    errors: dict[str, str]      # a field's key, and what is wrong with its value
    changed: list[str]          # the fields it changes


def _normal_pools(v: Any) -> list[tuple[str, list]]:
    if not isinstance(v, dict):
        return []
    return [(str(n), p if isinstance(p, list) else [p]) for n, p in v.items()]


def apply(text: str, form) -> Edit:
    """config.yaml as ``text`` with the values ``form`` posts, and what they change.

    A field the form leaves out stays as it is, and so does one an
    environment variable sets. An empty field takes its key out, bar the
    token, which stays until the YAML tab takes it out.

    Raises:
        FormError: the file cannot be edited this way, or the edit would not
            read back as the form gave it.
    """
    cfg = read(text)
    rows = submitted(form)
    values: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for f in FIELDS:
        if f.key not in form or f.env_value() is not None:
            continue
        raw = rows[f.key] if f.kind in ("pools", "times") else form.getlist(f.key)[-1]
        if f.kind == "secret" and not str(raw).strip():
            continue
        try:
            values[f.key] = parse(f, raw)
        except FieldError as exc:
            errors[f.key] = str(exc)
    if errors:
        return Edit(text, errors, [])

    doc = Doc(text)
    changed: list[str] = []
    expect: dict[tuple, Any] = {}
    times: list[tuple[str, str]] | None = None
    kind = values.get("display.schedule.type", lookup(cfg, ("display", "schedule", "type")))

    def put(path, value) -> None:
        doc.set(path, value)
        expect[tuple(path)] = value

    def take(key: str) -> None:
        if doc.remove(BY_KEY[key].path if key in BY_KEY else tuple(key.split("."))):
            changed.append(key)
            expect[tuple(key.split("."))] = MISSING

    for f in FIELDS:
        if f.key not in values or f.key.startswith("posts.quiet"):
            continue
        value = values[f.key]
        if f.kind == "pools":
            if not value:
                if lookup(cfg, f.path) is not MISSING:
                    errors[f.key] = "Add at least one pool."
                continue
            if _normal_pools(lookup(cfg, f.path)) != list(value.items()):
                doc.set_pools(value)
                expect[f.path] = value
                changed.append(f.key)
        elif f.kind == "times":
            if kind == "times" and dict(time_rows(cfg)) != dict(value):
                doc.set_times(value)
                times = value
                changed.append(f.key)
        elif kind == "times" and f.key in INTERVAL_KEYS:
            continue
        else:
            cur = lookup(cfg, f.path)
            if value is None:
                if cur is not MISSING:
                    take(f.key)
            elif not _same(cur, value) and not (cur is MISSING
                                                 and _same(default_of(f, cfg), value)):
                put(f.path, value)
                changed.append(f.key)

    if errors:
        return Edit(text, errors, [])
    if kind == "times":
        for key in INTERVAL_KEYS:
            take(key)
    elif time_rows(cfg):
        doc.set_times([])
        times = []
        changed.append("display.schedule.times")

    if "posts.quiet" in values:
        changed += _apply_quiet(doc, cfg, values, put, take)

    if not changed:
        return Edit(text, {}, [])
    new_text = doc.text()
    _check_reads_back(cfg, new_text, changed, expect, times)
    return Edit(new_text, {}, changed)


def _apply_quiet(doc: Doc, cfg: dict, values: dict, put, take) -> list[str]:
    """posts.quiet: ``{}`` when it is off; absent when it is on at the
    defaults; otherwise a block of the times the form gives."""
    path = ("posts", "quiet")
    cur = lookup(cfg, path)
    if not values["posts.quiet"]:
        if cur is not MISSING and not cur:
            return []
        put(path, {})
        return ["posts.quiet"]
    given = {k: values[f"posts.quiet.{k}"] for k in DEFAULT_QUIET if f"posts.quiet.{k}" in values}
    if _quiet_block(cfg) is None:
        block = {k: DEFAULT_QUIET[k] if given.get(k) is None else given[k] for k in DEFAULT_QUIET}
        if cur is MISSING and block == DEFAULT_QUIET:
            return []
        if block == DEFAULT_QUIET:
            take("posts.quiet")
            return []
        put(path, block)
        return ["posts.quiet"]
    changed = []
    for k, v in given.items():
        key, now = f"posts.quiet.{k}", lookup(cfg, path + (k,))
        if v is None:
            if now is not MISSING:
                take(key)
        elif not _same(now, v) and not (now is MISSING
                                        and _same(default_of(BY_KEY[key], cfg), v)):
            put(path + (k,), v)
            changed.append(key)
    return changed


def _flat(d: Any, prefix: tuple = ()) -> dict[tuple, Any]:
    if not isinstance(d, dict) or (not d and prefix):
        return {prefix: d}
    out: dict[tuple, Any] = {}
    for k, v in d.items():
        out.update(_flat(v, prefix + (str(k),)))
    return out


def _changed_paths(old: dict, new: dict) -> list[tuple]:
    a, b = _flat(old), _flat(new)
    return [p for p in dict.fromkeys([*a, *b])
            if not (p in a and p in b and _same(a[p], b[p]))]


def _reads_as(got: Any, value: Any) -> bool:
    if value is MISSING:
        return got is MISSING
    if isinstance(value, dict):
        return (isinstance(got, dict) and [str(k) for k in got] == list(value)
                and not _changed_paths(got, value))
    return _same(got, value)


def _check_reads_back(cfg: dict, text: str, changed: list[str], expect: dict,
                      times: list[tuple[str, str]] | None) -> None:
    """Refuse an edit that PyYAML would not read as the form gave it, or
    that touched a key the form did not change."""
    new = read(text)
    allowed = [tuple(k.split(".")) for k in changed]
    if "display.schedule.times" in changed or "display.schedule.type" in changed:
        allowed.append(("display", "schedule"))
    for path in _changed_paths(cfg, new):
        if not any(path[:len(p)] == p or p[:len(path)] == path for p in allowed):
            raise FormError(f"This edit also changes {name_of(path)}. Edit it in the YAML tab.")
    for path, value in expect.items():
        if not _reads_as(lookup(new, path), value):
            raise FormError(f"The form cannot save {name_of(path)} as entered. "
                            f"Edit it in the YAML tab.")
    if times is not None and dict(time_rows(new)) != dict(times):
        raise FormError("The form cannot save these wake times. Edit them in the YAML tab.")


# ── Words for the page ──────────────────────────────────────────────

def field_at(path: tuple) -> Field | None:
    """The field that holds ``path``, or holds the mapping it is in."""
    if path[:2] == ("display", "schedule") and len(path) > 2 and path[2] not in SCHEDULE_KEYS:
        return BY_KEY["display.schedule.times"]
    best = None
    for f in FIELDS:
        if path[:len(f.path)] == f.path and (best is None or len(f.path) > len(best.path)):
            best = f
    return best


def locate(message: str) -> tuple[str | None, str | None]:
    """The field and the tab a problem from load_settings is about, as far
    as the key it starts with says."""
    head = tuple(message.split(" ", 1)[0].rstrip(":,.").split("."))
    f = field_at(head)
    if f is not None:
        return f.key, TAB_OF[f.key]
    for n in range(len(head), 0, -1):
        for t in TABS:
            if any(f.path[:n] == head[:n] for f in t.fields):
                return None, t.name
    return None, None


def name_of(path: tuple) -> str:
    f = field_at(path)
    if f is None:
        return ".".join(path)
    tab = next(t for t in TABS if t.name == TAB_OF[f.key])
    group = next(g for g in tab.groups if f in g.fields)
    shared = sum(o.label == f.label for o in tab.fields) > 1
    rest = path[2:] if f.kind == "times" and path != f.path else path[len(f.path):]
    return " · ".join([tab.title, *([group.heading] if shared else []), f.label, *rest])


def _words(v: Any) -> str:
    if v is MISSING:
        return "not set"
    if isinstance(v, bool):
        return "on" if v else "off"
    if isinstance(v, list):
        return ", ".join(map(str, v))
    if v == {}:
        return "off"
    return str(v)


def _quiet_words(cfg: dict) -> str:
    q = lookup(cfg, ("posts", "quiet"))
    if q is not MISSING and not q:
        return "off"
    q = q if isinstance(q, dict) else DEFAULT_QUIET
    every = q.get("every", lookup(cfg, ("posts", "every")))
    return f"{q.get('from', '?')}–{q.get('to', '?')}, {300 if every is MISSING else every} s"


def _with_quiet_words(cfg: dict) -> dict:
    posts = cfg.get("posts")
    posts = dict(posts) if isinstance(posts, dict) else {}
    posts["quiet"] = _quiet_words(cfg)
    return {**cfg, "posts": posts}


def changes(old: dict, new: dict) -> list[dict[str, str]]:
    """Each setting that differs from ``old`` to ``new``, in words, in the form's order."""
    old, new = _with_quiet_words(old), _with_quiet_words(new)
    a, b = _flat(old), _flat(new)
    order = {f.key: i for i, f in enumerate(FIELDS)}
    out = []
    for path in _changed_paths(old, new):
        f = field_at(path)
        before, after = a.get(path, MISSING), b.get(path, MISSING)
        if f is not None and f.kind == "secret":
            before = MISSING if before in (MISSING, None, "") else "set"
            after = MISSING if after in (MISSING, None, "") else "new"
        if f is not None and f.kind in ("pools", "times"):
            before = "none" if before is MISSING else before
            after = "none" if after is MISSING else after
        out.append((order.get(f.key, len(order)) if f else len(order),
                    {"name": name_of(path), "old": _words(before), "new": _words(after)}))
    return [c for _, c in sorted(out, key=lambda x: x[0])]
