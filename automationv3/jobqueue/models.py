from dataclasses import dataclass
from datetime import datetime, timedelta

from ..reports import store

ALLOWED_STATUS = ["available", "busy", "missing"]

# Keepalives are sent every 60 seconds; a worker silent for longer
# than this is considered missing
MISSING_AFTER = timedelta(minutes=5)


@dataclass
class Job:
    id: str
    report_id: str
    script: str
    status: str
    worker_url: str
    queued_at: datetime
    claimed_at: datetime


def _job(row):
    id, report_id, script, status, worker_url, queued_at, claimed_at = row
    return Job(
        id,
        report_id,
        script,
        status,
        worker_url,
        datetime.fromisoformat(queued_at),
        datetime.fromisoformat(claimed_at) if claimed_at else None,
    )


JOB_COLUMNS = "id, report_id, script, status, worker_url, queued_at, claimed_at"


def enqueue(conn, root, report_id, script, closure):
    """Create a run folder in the report and queue it as a job"""
    run_id = store.create_run(root, report_id, script, closure)
    with conn:
        conn.execute(
            "INSERT INTO jobs(id, report_id, script) VALUES (?, ?, ?)",
            (run_id, report_id, script),
        )
    return run_id


def queue_script(conn, root, script, text):
    """Queue one script as a new report holding a single run"""
    report_id = store.create_report(root, scripts=[script])
    run_id = enqueue(conn, root, report_id, script, {script: text})
    return report_id, run_id


def get_job(conn, id):
    row = conn.execute(f"SELECT {JOB_COLUMNS} FROM jobs WHERE id = ?", (id,)).fetchone()
    return _job(row) if row else None


def find_jobs(conn, status=None):
    """Jobs oldest first, optionally only those with `status`"""
    query = f"SELECT {JOB_COLUMNS} FROM jobs"
    params = ()
    if status is not None:
        query += " WHERE status = ?"
        params = (status,)
    query += " ORDER BY id"
    return [_job(row) for row in conn.execute(query, params)]


def claim(conn, id, worker_url):
    """Atomically take a pending job. Returns False if someone else got it."""
    with conn:
        cursor = conn.execute(
            """
            UPDATE jobs
            SET status = 'claimed', worker_url = ?, claimed_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'pending'
            """,
            (worker_url, id),
        )
    return cursor.rowcount == 1


def start(conn, id, worker_url):
    with conn:
        cursor = conn.execute(
            """
            UPDATE jobs SET status = 'running'
            WHERE id = ? AND worker_url = ? AND status = 'claimed'
            """,
            (id, worker_url),
        )
    return cursor.rowcount == 1


def release(conn, id, worker_url):
    """Put a claimed job back in the queue. It is not a test result."""
    with conn:
        cursor = conn.execute(
            """
            UPDATE jobs
            SET status = 'pending', worker_url = NULL, claimed_at = NULL
            WHERE id = ? AND worker_url = ? AND status IN ('claimed', 'running')
            """,
            (id, worker_url),
        )
    return cursor.rowcount == 1


def finish(conn, root, job, outcome, **fields):
    """Record the outcome in run.json, then drop the job from the queue.

    run.json is written first so a crash in between leaves a job that
    `cleanup_finished` can remove, never a lost result.
    """
    store.update_run(
        root,
        job.report_id,
        job.id,
        outcome=outcome,
        worker=job.worker_url,
        ended=store.now_iso(),
        **fields,
    )
    with conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job.id,))


def fail_worker_jobs(conn, root, worker_url, reason):
    """Mark every job held by `worker_url` as error"""
    held = [
        job
        for job in find_jobs(conn)
        if job.worker_url == worker_url and job.status in ("claimed", "running")
    ]
    for job in held:
        finish(conn, root, job, "error", error=reason)
    return held


def reap_lost_jobs(conn, root, now=None):
    """Error the jobs of workers that stopped sending keepalives"""
    now = now or datetime.utcnow()
    alive = {w.url for w in find_workers(conn, since=now - MISSING_AFTER)}
    lost = {
        job.worker_url
        for job in find_jobs(conn)
        if job.status in ("claimed", "running") and job.worker_url not in alive
    }
    for url in lost:
        fail_worker_jobs(conn, root, url, f"Worker {url} stopped responding")
    return lost


def cleanup_finished(conn, root):
    """Remove queue rows whose run already has an outcome"""
    for job in find_jobs(conn):
        run = store.load_run(root, job.report_id, job.id)
        if run is not None and run.get("outcome") is not None:
            with conn:
                conn.execute("DELETE FROM jobs WHERE id = ?", (job.id,))


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
