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


def init_db(conn):
    """Create any missing tables"""
    conn.executescript(SCHEMA.read_text())
