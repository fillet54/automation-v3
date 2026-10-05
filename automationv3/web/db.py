"""A sqlite connection per request"""

from flask import current_app, g

from ..services.database import connect


def get_db():
    """Connection for the current app context, closed by close_db"""
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def close_db(error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()
