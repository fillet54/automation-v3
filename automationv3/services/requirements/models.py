"""Requirements as stored: what specs say in a context, and how that
changed

A context is where requirements are read from:

``trunk`` (or None)
    each spec's latest trunk;
``trunk@N``
    each spec's trunk as of import N;
``set:NAME``
    the baselines baseline set NAME pins;
``KEY@NAME``
    spec KEY's baseline NAME, alone.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ...framework.requirement import Requirement
from . import export, store

__all__ = ["Requirement", "find_by_id", "find_all", "subsystems", "insert",
           "resolve", "history", "diff", "log", "trace_issues", "satisfied_by",
           "specs", "contexts", "workspace_context", "ContextError"]


class ContextError(ValueError):
    pass


def resolve(conn, context=None):
    """spec key -> spec version hash, for the specs in `context`"""
    context = context or "trunk"
    if context == "trunk" or context.startswith("trunk@"):
        as_of = None
        if context != "trunk":
            try:
                as_of = int(context.split("@", 1)[1])
            except ValueError:
                raise ContextError(f"{context}: trunk@ takes an import number")
        keys = [k for (k,) in conn.execute(
            "SELECT DISTINCT spec FROM trunk_versions ORDER BY spec")]
        found = {k: store.trunk_head(conn, k, as_of) for k in keys}
        return {k: v for k, v in found.items() if v}
    if context.startswith("set:"):
        rows = conn.execute(
            "SELECT s.spec, b.spec_version FROM baseline_sets s JOIN baselines b "
            "ON b.spec = s.spec AND b.name = s.baseline WHERE s.name = ? ORDER BY s.spec",
            (context[4:],)).fetchall()
        if not rows:
            raise ContextError(f"there is no baseline set {context[4:]!r}")
        return dict(rows)
    if "@" in context:
        key, name = context.split("@", 1)
        row = conn.execute("SELECT spec_version FROM baselines WHERE spec = ? AND name = ?",
                           (key, name)).fetchone()
        if row is None:
            raise ContextError(f"there is no baseline {context}")
        return {key: row[0]}
    raise ContextError(f"{context!r}: a context is trunk, trunk@N, set:NAME or SPEC@BASELINE")


def as_requirement(spec, row):
    attributes = json.loads(row["attributes"])
    subsystem = attributes.get("subsystem")
    return Requirement(id=row["id"], text=row["text"],
                       subsystem=", ".join(subsystem) if isinstance(subsystem, list) else subsystem,
                       spec=spec, attributes=attributes,
                       satisfies=tuple(json.loads(row["satisfies"])),
                       section=tuple(json.loads(row["section"])), version=row["hash"],
                       text_hash=row["text_hash"])


def _in_context(conn, context, spec=None):
    for key, version in resolve(conn, context).items():
        if spec is None or key == spec:
            for row in store.contents(conn, version).values():
                yield as_requirement(key, row)


def find_all(conn, subsystem=None, context=None, spec=None):
    """The requirements in `context`, by spec then document order"""
    return [r for r in _in_context(conn, context, spec)
            if subsystem is None or r.subsystem == subsystem]


def find_by_id(conn, id, context=None):
    spec_of = {version: key for key, version in resolve(conn, context).items()}
    if not spec_of:
        return None
    row = conn.execute(
        "SELECT c.spec_version, r.* FROM spec_contents c JOIN requirement_versions r "
        "ON r.hash = c.requirement_version WHERE r.id = ? AND c.spec_version IN (%s)"
        % ",".join("?" * len(spec_of)), (id, *spec_of)).fetchone()
    return as_requirement(spec_of[row["spec_version"]], row) if row else None


def subsystems(conn, context=None):
    return sorted({r.subsystem for r in _in_context(conn, context) if r.subsystem})


@dataclass(frozen=True)
class Change:
    """A requirement added, removed or changed. `changes` is ["added"],
    ["removed"], or the facets that changed (text, metadata, links,
    section); before/after are Requirements (None if absent)."""
    id: str
    spec: str
    changes: tuple
    before: Requirement = None
    after: Requirement = None


def diff(conn, a, b, spec=None, subsystem=None):
    """The Changes from context `a` to context `b`, optionally only in one
    spec or subsystem. A requirement moved between specs shows as
    changed (its spec is the one in `b`)."""
    old = {r.id: r for r in _in_context(conn, a, spec)}
    new = {r.id: r for r in _in_context(conn, b, spec)}
    rows = {}
    for r in [*old.values(), *new.values()]:
        rows.setdefault(r.version, None)
    stored = {row["hash"]: row for row in conn.execute(
        f"SELECT * FROM requirement_versions WHERE hash IN ({','.join('?' * len(rows))})",
        list(rows))} if rows else {}
    out = []
    for id in sorted(old.keys() | new.keys()):
        before, after = old.get(id), new.get(id)
        if subsystem and subsystem not in {getattr(before, "subsystem", None),
                                           getattr(after, "subsystem", None)}:
            continue
        if before is None:
            out.append(Change(id, after.spec, ("added",), None, after))
        elif after is None:
            out.append(Change(id, before.spec, ("removed",), before, None))
        else:
            what = store.facet_changes(stored[before.version], stored[after.version])
            if before.spec != after.spec:
                what = ["spec", *what]
            if what:
                out.append(Change(id, after.spec, tuple(what), before, after))
    return out


@dataclass(frozen=True)
class Event:
    """One entry in a requirement's history"""
    import_id: int
    imported_at: str
    kind: str  # "trunk" or "baseline"
    label: str  # the spec, or SPEC@BASELINE
    changes: tuple
    requirement: Requirement = None  # the version after (or before, if removed)
    before: Requirement = None  # for a trunk change, the version before


def history(conn, id):
    """Every trunk change to requirement `id`, and every baseline it is
    in, oldest first"""
    events = []
    for row in conn.execute(
            "SELECT c.*, i.imported_at FROM requirement_changes c "
            "JOIN imports i ON i.id = c.import_id WHERE c.id = ? ORDER BY c.import_id",
            (id,)):
        version = row["after"] or row["before"]
        req = conn.execute("SELECT * FROM requirement_versions WHERE hash = ?",
                           (version,)).fetchone()
        before = conn.execute("SELECT * FROM requirement_versions WHERE hash = ?",
                              (row["before"],)).fetchone() if row["after"] else None
        events.append(Event(row["import_id"], row["imported_at"], "trunk", row["spec"],
                            tuple(json.loads(row["changes"])), as_requirement(row["spec"], req),
                            as_requirement(row["spec"], before) if before else None))
    for row in conn.execute(
            "SELECT b.spec, b.name, b.import_id, i.imported_at, r.* FROM baselines b "
            "JOIN imports i ON i.id = b.import_id "
            "JOIN spec_contents c ON c.spec_version = b.spec_version "
            "JOIN requirement_versions r ON r.hash = c.requirement_version "
            "WHERE r.id = ?", (id,)):
        events.append(Event(row["import_id"], row["imported_at"], "baseline",
                            f"{row['spec']}@{row['name']}", (), as_requirement(row["spec"], row)))
    return sorted(events, key=lambda e: (e.import_id, e.kind != "trunk"))


def log(conn, limit=20):
    """The latest imports, newest first: (id, imported_at, source,
    [(spec, id, changes)]) with each requirement change trunk saw"""
    out = []
    for imp in conn.execute("SELECT id, imported_at, source FROM imports "
                            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall():
        changes = [(r["spec"], r["id"], tuple(json.loads(r["changes"])))
                   for r in conn.execute("SELECT spec, id, changes FROM requirement_changes "
                                         "WHERE import_id = ? ORDER BY spec, id", (imp["id"],))]
        out.append((imp["id"], imp["imported_at"], imp["source"], changes))
    return out


def unhashed_attributes(conn):
    """spec -> the attributes any version of its schema marks as not
    hashed: shown, but never a change"""
    out = {}
    for spec, schema in conn.execute("SELECT spec, attributes FROM spec_versions"):
        out.setdefault(spec, set()).update(
            name for name, a in json.loads(schema).items() if not a.get("hashed", True))
    return out


def satisfied_by(conn, id, context=None):
    """The requirements in `context` that trace up to `id`"""
    return [r for r in _in_context(conn, context) if id in r.satisfies]


@dataclass(frozen=True)
class SpecInfo:
    key: str
    title: str
    level: str
    parents: tuple
    version: str
    count: int


def specs(conn, context=None):
    """The specs in `context`, top level first"""
    out = []
    for key, version in resolve(conn, context).items():
        row = conn.execute("SELECT * FROM spec_versions WHERE hash = ?", (version,)).fetchone()
        count = conn.execute("SELECT COUNT(*) FROM spec_contents WHERE spec_version = ?",
                             (version,)).fetchone()[0]
        out.append(SpecInfo(key, row["title"], row["level"], tuple(json.loads(row["parents"])),
                            version, count))
    order = {level: n for n, level in enumerate(export.LEVELS)}
    return sorted(out, key=lambda s: (order.get(s.level, 9), s.key))


def contexts(conn):
    """[(context, label)] to choose from: trunk, then each baseline set,
    then each spec's baselines; newest first within each"""
    out = [("trunk", "Trunk (latest)")]
    out += [(f"set:{name}", name) for (name,) in conn.execute(
        "SELECT name FROM baseline_sets GROUP BY name ORDER BY MAX(import_id) DESC, name")]
    out += [(f"{spec}@{name}", f"{spec} {name}") for spec, name in conn.execute(
        "SELECT spec, name FROM baselines ORDER BY spec, import_id DESC, name")]
    return out


def trace_issues(conn, context=None):
    """[(id, target, problem)] for links that don't resolve in `context`,
    or that point at a spec that isn't one of the spec's parents"""
    reqs = list(_in_context(conn, context))
    spec_of = {r.id: r.spec for r in reqs}
    parents = {key: set(json.loads(p)) for key, p in conn.execute(
        "SELECT spec, parents FROM spec_versions WHERE hash IN (%s)"
        % ",".join("?" * len(resolve(conn, context))),
        list(resolve(conn, context).values()))}
    issues = []
    for r in reqs:
        for target in r.satisfies:
            if target not in spec_of:
                issues.append((r.id, target, "missing"))
            elif spec_of[target] not in parents.get(r.spec, ()):
                issues.append((r.id, target, f"{spec_of[target]} is not a parent of {r.spec}"))
    return issues


WORKSPACE_CONFIG = "automation.json"


def workspace_context(conn, root):
    """(context, problem): the context a workspace verifies, from
    "requirements" in automation.json at its root (trunk if it says
    nothing), and why it fell back to trunk, if it did"""
    path = Path(root) / WORKSPACE_CONFIG
    if not path.is_file():
        return "trunk", None
    try:
        context = json.loads(path.read_text()).get("requirements") or "trunk"
    except (ValueError, AttributeError) as e:
        return "trunk", f"{WORKSPACE_CONFIG} can't be read ({e}); showing trunk"
    try:
        resolve(conn, context)
    except ContextError as e:
        return "trunk", f"{WORKSPACE_CONFIG} names {context!r}: {e}; showing trunk"
    return context, None


LOCAL = "LOCAL"


def now():
    return datetime.now(timezone.utc).isoformat()


def insert(conn, requirements, spec=LOCAL):
    """Add `requirements` (framework Requirements) to trunk spec `spec`,
    through an import like any other: for tests and hand-made data"""
    current = {r.id: r for r in find_all(conn, spec=spec)} if spec in resolve(conn) else {}
    current.update({r.id: r for r in requirements})
    lines = [spec, "=" * len(spec), ""]
    for r in current.values():
        lines.append(f".. requirement:: {r.id}")
        if r.subsystem:
            lines.append(f"   :subsystem: {r.subsystem}")
        lines += ["", *("   " + line for line in (r.text or r.id).splitlines()), ""]
    s = export.Spec(key=spec, title=spec, level="software", parents=[],
                    attributes={"subsystem": {"type": "string", "hashed": True}},
                    files={"index.rst": "\n".join(lines).encode()})
    s.requirements = export.spec_requirements(s)
    store.import_export(conn, export.Export("<insert>", {"format": 1}, [s], [],
                                            export.exported_at(now())))
