"""Plain sqlite3 database access"""

import sqlite3
from pathlib import Path

from flask import current_app, g

SCHEMA = Path(__file__).resolve().parent / "schema.sql"


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn):
    """Create any missing tables"""
    conn.executescript(SCHEMA.read_text())


def get_db():
    """Connection for the current app context, closed by close_db"""
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def close_db(error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()
