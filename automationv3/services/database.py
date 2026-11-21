"""Plain sqlite3 database access

All tables are defined in schema.sql, applied (idempotently) by init_db.
"""

import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).resolve().parent / "schema.sql"


def connect(path, wal=False):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
    return conn


# Columns added since their table was first created, for databases made
# before them: table -> [(column, definition)]
ADDED_COLUMNS = {"jobs": [("fingerprint_hash", "TEXT"), ("owner", "TEXT")],
                 "workers": [("token", "TEXT")],
                 "imports": [("imported_by", "TEXT")],
                 "script_reviews": [("reviewed_by", "TEXT")],
                 "trace_reviews": [("reviewed_by", "TEXT")]}


def init_db(conn):
    """Create any missing tables and columns"""
    conn.executescript(SCHEMA.read_text())
    for table, columns in ADDED_COLUMNS.items():
        have = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns:
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
    conn.commit()


# Workspace UI state (expanded tree nodes and open editor tabs)


def expanded_node_paths(conn, workspace_id):
    rows = conn.execute(
        "SELECT path FROM expanded_nodes WHERE workspace_id = ?", (workspace_id,)
    )
    return [row[0] for row in rows]


def toggle_expanded_node(conn, workspace_id, path):
    params = (workspace_id, path)
    with conn:
        deleted = conn.execute(
            "DELETE FROM expanded_nodes WHERE workspace_id = ? AND path = ?", params
        ).rowcount
        if not deleted:
            conn.execute(
                "INSERT INTO expanded_nodes(workspace_id, path) VALUES (?, ?)", params
            )


def expand_nodes(conn, workspace_id, paths):
    """Open each of `paths` in the tree (those open already stay open)"""
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO expanded_nodes(workspace_id, path) VALUES (?, ?)",
            [(workspace_id, path) for path in paths])


def open_tabs(conn, workspace_id):
    """([path], the active path or None), in tab order"""
    rows = conn.execute("SELECT path, active FROM open_tabs WHERE workspace_id = ? "
                        "ORDER BY position", (workspace_id,)).fetchall()
    return [r[0] for r in rows], next((r[0] for r in rows if r[1]), None)


def set_open_tabs(conn, workspace_id, paths, active, max_tabs=30):
    paths = list(dict.fromkeys(p for p in paths if isinstance(p, str) and p))[:max_tabs]
    with conn:
        conn.execute("DELETE FROM open_tabs WHERE workspace_id = ?", (workspace_id,))
        conn.executemany(
            "INSERT INTO open_tabs(workspace_id, path, position, active) VALUES (?, ?, ?, ?)",
            [(workspace_id, p, n, int(p == active)) for n, p in enumerate(paths)])
