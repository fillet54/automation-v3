"""Suspect links: what may need another look after a requirement changed

A link is suspect when the text of the requirement it points at has
changed since the link was last reviewed. Two kinds of link are watched:

scripts
    a script's :req: reference, per workspace, against the requirement's
    text in the workspace's context;
traces
    a requirement's :satisfies: link, against its parent's text in trunk.

A link is taken as reviewed against the text it first meets ("first
seen"), so only later changes make it suspect; reviewing it records the
current text ("reviewed").
"""

import json
from dataclasses import dataclass

from . import models, store


def text_hashes(conn, context=None):
    """requirement id -> its text hash, in `context`"""
    out = {}
    for version in models.resolve(conn, context).values():
        for id, row in store.contents(conn, version).items():
            out[id] = row["text_hash"]
    return out


@dataclass(frozen=True)
class Suspect:
    """A suspect link: `source` (a script, or a child requirement) to
    requirement `target`, last reviewed against `reviewed` (a text hash)"""
    source: str
    target: str
    reviewed: str
    reviewed_at: str


# -- scripts


def sync_scripts(conn, workspace, context=None, hashes=None):
    """Record links of `workspace` never seen before as reviewed against
    their requirement's current text"""
    hashes = text_hashes(conn, context) if hashes is None else hashes
    rows = conn.execute(
        "SELECT l.script, l.requirement_id FROM requirement_links l "
        "LEFT JOIN script_reviews r ON r.workspace = l.workspace AND r.script = l.script "
        "AND r.requirement_id = l.requirement_id WHERE l.workspace = ? AND r.script IS NULL",
        (workspace,)).fetchall()
    with conn:
        conn.executemany(
            "INSERT INTO script_reviews(workspace, script, requirement_id, text_hash, how) "
            "VALUES (?, ?, ?, ?, 'first seen')",
            [(workspace, script, id, hashes[id]) for script, id in rows if id in hashes])


def script_suspects(conn, workspace, context=None):
    """[Suspect] for the scripts of `workspace` whose requirement's text
    changed since they were reviewed"""
    hashes = text_hashes(conn, context)
    sync_scripts(conn, workspace, context, hashes)
    rows = conn.execute(
        "SELECT r.script, r.requirement_id, r.text_hash, r.reviewed_at FROM script_reviews r "
        "JOIN requirement_links l ON l.workspace = r.workspace AND l.script = r.script "
        "AND l.requirement_id = r.requirement_id WHERE r.workspace = ? "
        "ORDER BY r.requirement_id, r.script", (workspace,))
    return [Suspect(script, id, h, at) for script, id, h, at in rows
            if id in hashes and hashes[id] != h]


def review_script(conn, workspace, script, id, context=None):
    """Record that `script` was reviewed against `id`'s current text"""
    current = text_hashes(conn, context).get(id)
    if current is None:
        raise models.ContextError(f"there is no requirement {id} in {context or 'trunk'}")
    with conn:
        conn.execute(
            "INSERT INTO script_reviews(workspace, script, requirement_id, text_hash, how) "
            "VALUES (?, ?, ?, ?, 'reviewed') ON CONFLICT(workspace, script, requirement_id) "
            "DO UPDATE SET text_hash = excluded.text_hash, how = 'reviewed', "
            "reviewed_at = CURRENT_TIMESTAMP", (workspace, script, id, current))


# -- traces


def trunk_links(conn):
    """[(child, parent)] for every :satisfies: link in trunk"""
    out = []
    for version in models.resolve(conn, "trunk").values():
        for id, row in store.contents(conn, version).items():
            out += [(id, parent) for parent in json.loads(row["satisfies"])]
    return out


def sync_traces(conn):
    """Record trunk's trace links never seen before as reviewed against
    their parent's current text. Runs after every import."""
    hashes = text_hashes(conn, "trunk")
    conn.executemany(
        "INSERT OR IGNORE INTO trace_reviews(child, parent, text_hash, how) "
        "VALUES (?, ?, ?, 'first seen')",
        [(child, parent, hashes[parent]) for child, parent in trunk_links(conn)
         if parent in hashes])


def trace_suspects(conn):
    """[Suspect] for trunk requirements whose parent's text changed since
    the link was reviewed"""
    hashes = text_hashes(conn, "trunk")
    links = set(trunk_links(conn))
    rows = conn.execute("SELECT child, parent, text_hash, reviewed_at FROM trace_reviews "
                        "ORDER BY parent, child")
    return [Suspect(child, parent, h, at) for child, parent, h, at in rows
            if (child, parent) in links and parent in hashes and hashes[parent] != h]


def review_trace(conn, child, parent):
    current = text_hashes(conn, "trunk").get(parent)
    if current is None:
        raise models.ContextError(f"there is no requirement {parent} in trunk")
    with conn:
        conn.execute(
            "INSERT INTO trace_reviews(child, parent, text_hash, how) VALUES (?, ?, ?, 'reviewed') "
            "ON CONFLICT(child, parent) DO UPDATE SET text_hash = excluded.text_hash, "
            "how = 'reviewed', reviewed_at = CURRENT_TIMESTAMP", (child, parent, current))


def reviewed_version(conn, id, text_hash):
    """A version of requirement `id` with the text it was reviewed
    against, to show what changed since; None if none is stored"""
    row = conn.execute("SELECT * FROM requirement_versions WHERE id = ? AND text_hash = ? "
                       "LIMIT 1", (id, text_hash)).fetchone()
    return models.as_requirement(None, row) if row else None
