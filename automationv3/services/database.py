"""Plain sqlite3 database access

All tables are defined in schema.sql, applied (idempotently) by init_db.
"""

import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).resolve().parent / "schema.sql"


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


# Columns added since their table was first created, for databases made
# before them: table -> [(column, definition)]
ADDED_COLUMNS = {"jobs": [("fingerprint_hash", "TEXT")]}


def init_db(conn):
    """Create any missing tables and columns"""
    conn.executescript(SCHEMA.read_text())
    for table, columns in ADDED_COLUMNS.items():
        have = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns:
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
    conn.commit()
