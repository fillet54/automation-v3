"""Importing exports into sqlite

An import stores every spec in the export by content. A trunk spec is
compared with the trunk before it, and each requirement added, removed or
changed is logged against the import; a baseline is stored once and may
never change. Everything happens in one transaction: an export with a
problem leaves the database as it was.
"""

import json

from .export import ExportError, digest


class ImportError_(ExportError):
    """An export that reads correctly but contradicts what is stored"""


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def import_export(conn, export, source=None):
    """Import `export` (an export.Export). Returns (import id, a list of
    (spec label, outcome) lines saying what happened to each spec)."""
    with conn:
        import_id = conn.execute(
            "INSERT INTO imports(exported_at, source, manifest) VALUES (?, ?, ?)",
            (export.exported_at, str(source or export.path),
             _json(export.manifest))).lastrowid
        outcomes = [(spec.label, import_spec(conn, import_id, spec, export.exported_at))
                    for spec in export.specs]
        outcomes += [(f"set {s['name']}", import_set(conn, import_id, s))
                     for s in export.baseline_sets]
        check_unique_ids(conn)
        from . import suspects  # it reads through models, which reads through here
        suspects.sync_traces(conn)
    return import_id, outcomes


def store_spec_version(conn, spec):
    for content in spec.files.values():
        conn.execute("INSERT OR IGNORE INTO blobs VALUES (?, ?)", (digest(content), content))
    conn.execute(
        "INSERT OR IGNORE INTO spec_versions VALUES (?, ?, ?, ?, ?, ?, ?)",
        (spec.hash, spec.key, spec.title, spec.level, _json(spec.parents),
         _json(spec.attributes), _json(spec.tree)))
    for r in spec.requirements:
        conn.execute(
            "INSERT OR IGNORE INTO requirement_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (r.hash, r.id, r.text, _json(r.attributes), _json(list(r.satisfies)),
             _json(list(r.section)), r.text_hash, r.metadata_hash, r.links_hash,
             r.section_hash))
    conn.execute("DELETE FROM spec_contents WHERE spec_version = ?", (spec.hash,))
    conn.executemany("INSERT INTO spec_contents VALUES (?, ?, ?)",
                     [(spec.hash, i, r.hash) for i, r in enumerate(spec.requirements)])


def import_spec(conn, import_id, spec, exported=None):
    store_spec_version(conn, spec)
    if spec.baseline:
        return import_baseline(conn, import_id, spec)
    conn.execute(
        "INSERT INTO specs VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET "
        "title = excluded.title, level = excluded.level, parents = excluded.parents",
        (spec.key, spec.title, spec.level, _json(spec.parents)))
    last = conn.execute(
        "SELECT spec_version, exported_at FROM trunk_versions WHERE spec = ? "
        "ORDER BY import_id DESC LIMIT 1", (spec.key,)).fetchone()
    before = last["spec_version"] if last else None
    if last and exported < last["exported_at"]:
        raise ImportError_(f"{spec.label}: exported {exported}, before the trunk already "
                           f"imported ({last['exported_at']}); trunk only moves forward")
    if last and exported == last["exported_at"] and before != spec.hash:
        raise ImportError_(f"{spec.label}: exported {exported}, like the trunk already "
                           f"imported, but with different content")
    conn.execute("INSERT INTO trunk_versions VALUES (?, ?, ?, ?)",
                 (import_id, spec.key, spec.hash, exported))
    if before == spec.hash:
        return "unchanged"
    changes = compare(conn, before, spec.hash)
    conn.executemany(
        "INSERT INTO requirement_changes VALUES (?, ?, ?, ?, ?, ?)",
        [(import_id, spec.key, id, b, a, _json(what)) for id, b, a, what in changes])
    if before is None:
        return f"new: {len(spec.requirements)} requirements"
    return summary(changes) or "documents changed; no requirement did"


def import_baseline(conn, import_id, spec):
    conn.execute("INSERT OR IGNORE INTO specs VALUES (?, ?, ?, ?)",
                 (spec.key, spec.title, spec.level, _json(spec.parents)))
    row = conn.execute("SELECT spec_version FROM baselines WHERE spec = ? AND name = ?",
                       (spec.key, spec.baseline)).fetchone()
    if row is None:
        conn.execute("INSERT INTO baselines VALUES (?, ?, ?, ?)",
                     (spec.key, spec.baseline, spec.hash, import_id))
        return f"new baseline: {len(spec.requirements)} requirements"
    if row[0] != spec.hash:
        raise ImportError_(f"{spec.label} was imported before with different content; "
                           f"a baseline can't change")
    return "unchanged"


def import_set(conn, import_id, s):
    pins = dict(sorted(s["specs"].items()))
    for key, name in pins.items():
        if conn.execute("SELECT 1 FROM baselines WHERE spec = ? AND name = ?",
                        (key, name)).fetchone() is None:
            raise ImportError_(f"set {s['name']}: there is no baseline {key}@{name}")
    have = dict(conn.execute("SELECT spec, baseline FROM baseline_sets WHERE name = ?",
                             (s["name"],)).fetchall())
    if have:
        if have != pins:
            raise ImportError_(f"set {s['name']} was imported before with other baselines")
        return "unchanged"
    conn.executemany("INSERT INTO baseline_sets VALUES (?, ?, ?, ?)",
                     [(s["name"], key, name, import_id) for key, name in pins.items()])
    versions = [v for (v,) in conn.execute(
        "SELECT b.spec_version FROM baseline_sets s JOIN baselines b "
        "ON b.spec = s.spec AND b.name = s.baseline WHERE s.name = ?", (s["name"],))]
    clash = clashing_ids(conn, versions)
    if clash:
        raise ImportError_(f"set {s['name']}: " + "; ".join(clash))
    return "new set: " + ", ".join(f"{k}@{v}" for k, v in pins.items())


def trunk_head(conn, spec, as_of=None):
    row = conn.execute(
        "SELECT spec_version FROM trunk_versions WHERE spec = ? AND import_id <= ? "
        "ORDER BY import_id DESC LIMIT 1",
        (spec, as_of if as_of is not None else 2 ** 62)).fetchone()
    return row[0] if row else None


FACETS = ("text", "metadata", "links", "section")


def contents(conn, spec_version):
    """id -> requirement_versions row of a spec version"""
    if spec_version is None:
        return {}
    rows = conn.execute(
        "SELECT r.* FROM spec_contents c JOIN requirement_versions r "
        "ON r.hash = c.requirement_version WHERE c.spec_version = ? ORDER BY c.position",
        (spec_version,))
    return {row["id"]: row for row in rows}


def facet_changes(before, after):
    return [f for f in FACETS if before[f + "_hash"] != after[f + "_hash"]]


def compare(conn, before_version, after_version):
    """[(id, before hash, after hash, changes)] between two spec versions,
    for each requirement added, removed or changed"""
    before, after = contents(conn, before_version), contents(conn, after_version)
    out = []
    for id, row in after.items():
        if id not in before:
            out.append((id, None, row["hash"], ["added"]))
        else:
            what = facet_changes(before[id], row)
            if what:
                out.append((id, before[id]["hash"], row["hash"], what))
    out += [(id, row["hash"], None, ["removed"]) for id, row in before.items()
            if id not in after]
    return out


def summary(changes):
    counts = {}
    for *_, what in changes:
        kind = what[0] if what[0] in ("added", "removed") else "changed"
        counts[kind] = counts.get(kind, 0) + 1
    return ", ".join(f"{n} {k}" for k, n in counts.items())


def clashing_ids(conn, spec_versions):
    """Problems for ids in more than one of the spec versions"""
    owner, problems = {}, []
    for v in spec_versions:
        spec = conn.execute("SELECT spec FROM spec_versions WHERE hash = ?", (v,)).fetchone()[0]
        for id in contents(conn, v):
            if id in owner and owner[id] != spec:
                problems.append(f"requirement {id} is in both {owner[id]} and {spec}")
            owner.setdefault(id, spec)
    return problems


def check_unique_ids(conn):
    heads = [trunk_head(conn, key) for (key,) in conn.execute(
        "SELECT DISTINCT spec FROM trunk_versions ORDER BY spec")]
    problems = clashing_ids(conn, heads)
    if problems:
        raise ImportError_("trunk: " + "; ".join(problems))
