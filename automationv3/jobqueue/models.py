from dataclasses import dataclass
from datetime import datetime


class Job:
    @property
    def title(self):
        return "??????"


ALLOWED_STATUS = ["available", "busy", "missing"]


@dataclass
class Worker:
    id: int
    url: str
    status: str
    last_keepalive: datetime


def _worker(row):
    id, url, status, last_keepalive = row
    return Worker(id, url, status, datetime.fromisoformat(last_keepalive))


def save_worker(conn, url, status):
    """Register a new worker or record a keepalive for an existing one"""
    with conn:
        conn.execute(
            """
            INSERT INTO workers(url, status) VALUES (?, ?)
            ON CONFLICT(url) DO UPDATE
            SET status = excluded.status, last_keepalive = CURRENT_TIMESTAMP
            """,
            (url, status),
        )


def find_workers(conn, since=None):
    """All workers, or only those with a keepalive at or after `since`"""
    query = "SELECT id, url, status, last_keepalive FROM workers"
    if since is None:
        return [_worker(row) for row in conn.execute(query)]
    since = since.isoformat(sep=" ", timespec="seconds")
    query += " WHERE last_keepalive >= ?"
    return [_worker(row) for row in conn.execute(query, (since,))]
