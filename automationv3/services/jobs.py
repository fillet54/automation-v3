import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from ..framework.closure import Closure, resolve
from ..framework.planning import build_plan
from .reports import store

ALLOWED_STATUS = ["available", "busy", "missing"]

# Keepalives are sent every 60 seconds; a worker silent for longer
# than this is considered missing
MISSING_AFTER = timedelta(minutes=5)


@dataclass
class Job:
    id: str
    report_id: str
    script: str
    environment: str
    variation: str
    uut_versions: dict
    status: str
    worker_url: str
    queued_at: datetime
    claimed_at: datetime


def _job(row):
    (id, report_id, script, environment, variation, uut_versions,
     status, worker_url, queued_at, claimed_at) = row
    return Job(
        id,
        report_id,
        script,
        environment,
        variation,
        json.loads(uut_versions),
        status,
        worker_url,
        datetime.fromisoformat(queued_at),
        datetime.fromisoformat(claimed_at) if claimed_at else None,
    )


JOB_COLUMNS = (
    "id, report_id, script, environment, variation, uut_versions, "
    "status, worker_url, queued_at, claimed_at"
)


class QueueError(Exception):
    """A request that can't be queued, with every reason why"""

    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def enqueue(conn, root, report_id, script, files, load_order,
            environment=None, uut_versions=None, imports=(), variation=None):
    """Create a run folder in the report and queue it as a job.

    `variation` is None or {"name", "values"} (values as edn text).
    """
    uut_versions = uut_versions or {}
    run_id = store.create_run(root, report_id, script, files)
    store.update_run(
        root,
        report_id,
        run_id,
        load_order=load_order,
        imports=list(imports),
        closure_hash=closure_hash(files, load_order),
        environment=environment,
        variation=variation,
        uut_versions=uut_versions,
    )
    with conn:
        conn.execute(
            """
            INSERT INTO jobs(id, report_id, script, environment, variation,
                             uut_versions)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                report_id,
                script,
                environment,
                variation["name"] if variation else None,
                json.dumps(uut_versions),
            ),
        )
    return run_id


def closure_hash(files, load_order):
    return Closure(load_order[-1], files, load_order).hash


def queue_plan(conn, root, plan):
    """Queue every run of `plan` under one new report.

    Returns (report_id, run_ids). Raises QueueError if the plan has
    errors or nothing to run.
    """
    runs = plan.runs()
    if plan.errors or not runs:
        errors = list(plan.errors) or ["Nothing to run"]
        errors += [f"{s.script}: {s.skipped}" for s in plan.scripts if s.skipped]
        raise QueueError(errors)

    report_id = store.create_report(root, **plan.summary())
    run_ids = []
    for script_plan, environment, variation in runs:
        closure = script_plan.closure
        if variation is not None:
            choice = next(v for v in script_plan.variations if v.name == variation)
            variation = {"name": choice.name, "values": choice.values}
        run_ids.append(enqueue(
            conn,
            root,
            report_id,
            closure.script,
            closure.files,
            closure.load_order,
            environment,
            {name: plan.uut_versions[name] for name in closure.uuts},
            closure.imports,
            variation,
        ))
    return report_id, run_ids


def queue_script(conn, root, workspace_root, script, text=None,
                 environment=None, versions=None, workspace=""):
    """Queue one script, in one environment, as a new report.

    The environment defaults to the first the script declares. Every
    variation is queued. `text` overrides the script's content on disk.
    Returns (report_id, first run id).
    """
    closure = resolve(workspace_root, script, text)
    if closure.errors:
        raise QueueError(closure.errors)
    if environment and environment not in closure.environments:
        raise QueueError([f"{script} does not support environment {environment}"])
    environment = environment or next(iter(closure.environments), None)

    plan = build_plan(
        workspace,
        workspace_root,
        [script],
        environments=[environment] if environment else None,
        versions=versions,
        texts={script: text} if text is not None else None,
    )
    report_id, run_ids = queue_plan(conn, root, plan)
    return report_id, run_ids[0]


def rerun(conn, root, report_id, run_id):
    """Queue an identical run (same closure, environment, variation, versions)"""
    run = store.load_run(root, report_id, run_id)
    files = store.read_closure(root, report_id, run_id)
    return enqueue(conn, root, report_id, run["script"], files,
                   run.get("load_order", [run["script"]]),
                   run.get("environment"), run.get("uut_versions"),
                   run.get("imports", []), run.get("variation"))


def get_job(conn, id):
    row = conn.execute(f"SELECT {JOB_COLUMNS} FROM jobs WHERE id = ?", (id,)).fetchone()
    return _job(row) if row else None


def jobs_for_worker(conn, worker_url):
    """Pending jobs, oldest first, that `worker_url` is able to run"""
    worker = get_worker(conn, worker_url)
    if worker is None:
        return []
    return [
        job
        for job in find_jobs(conn, "pending")
        if (job.environment is None or job.environment in worker.environments)
        and set(job.uut_versions) <= set(worker.uut_types)
    ]


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
    uut_types: list = field(default_factory=list)
    environments: dict = field(default_factory=dict)  # name -> fingerprint


WORKER_COLUMNS = "id, url, status, last_keepalive, uut_types"


def _worker(conn, row):
    id, url, status, last_keepalive, uut_types = row
    environments = {
        name: json.loads(fingerprint)
        for name, fingerprint in conn.execute(
            "SELECT name, fingerprint FROM worker_environments WHERE worker_id = ?",
            (id,),
        )
    }
    return Worker(
        id,
        url,
        status,
        datetime.fromisoformat(last_keepalive),
        json.loads(uut_types),
        environments,
    )


def save_worker(conn, url, status, uut_types=None, environments=None):
    """Register a new worker or record a keepalive for an existing one.

    `uut_types` and `environments` (name -> fingerprint) replace what was
    known about the worker when given.
    """
    with conn:
        conn.execute(
            """
            INSERT INTO workers(url, status) VALUES (?, ?)
            ON CONFLICT(url) DO UPDATE
            SET status = excluded.status, last_keepalive = CURRENT_TIMESTAMP
            """,
            (url, status),
        )
        (worker_id,) = conn.execute(
            "SELECT id FROM workers WHERE url = ?", (url,)
        ).fetchone()
        if uut_types is not None:
            conn.execute(
                "UPDATE workers SET uut_types = ? WHERE id = ?",
                (json.dumps(sorted(uut_types)), worker_id),
            )
        if environments is not None:
            conn.execute(
                "DELETE FROM worker_environments WHERE worker_id = ?", (worker_id,)
            )
            conn.executemany(
                """
                INSERT INTO worker_environments(
                    worker_id, name, fingerprint, fingerprint_hash)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        worker_id,
                        name,
                        json.dumps(fp, sort_keys=True),
                        fingerprint_hash(fp),
                    )
                    for name, fp in environments.items()
                ],
            )


def fingerprint_hash(fingerprint):
    canonical = json.dumps(fingerprint, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def get_worker(conn, url):
    row = conn.execute(
        f"SELECT {WORKER_COLUMNS} FROM workers WHERE url = ?", (url,)
    ).fetchone()
    return _worker(conn, row) if row else None


def find_workers(conn, since=None):
    """All workers, or only those with a keepalive at or after `since`"""
    query = f"SELECT {WORKER_COLUMNS} FROM workers"
    if since is None:
        return [_worker(conn, row) for row in conn.execute(query).fetchall()]
    since = since.isoformat(sep=" ", timespec="seconds")
    query += " WHERE last_keepalive >= ?"
    return [_worker(conn, row) for row in conn.execute(query, (since,)).fetchall()]


# Operations workers perform. The HTTP API and in-process servers both
# call these, so the rules live in one place: only the worker holding a
# job may act on it.

OUTCOMES = ["pass", "fail", "blocked", "error"]


class NoSuchJob(LookupError):
    pass


class NotHeld(PermissionError):
    pass


def job_json(job):
    return {
        **asdict(job),
        "queued_at": str(job.queued_at),
        "claimed_at": str(job.claimed_at),
    }


def check_in(conn, root, url, status, uut_types=None, environments=None,
             started=False):
    """Register or refresh a worker. A (re)starting worker can't still be
    running anything it held before, so those jobs become errors."""
    if status not in ALLOWED_STATUS:
        raise ValueError(f"Status must be one of {ALLOWED_STATUS}")
    save_worker(conn, url, status, uut_types=uut_types, environments=environments)
    if started:
        fail_worker_jobs(conn, root, url, f"Worker {url} restarted")


def available_jobs(conn, root, worker_url=None, status="pending"):
    """Pending jobs (those `worker_url` can run, if given), oldest first"""
    reap_lost_jobs(conn, root)
    if worker_url is not None:
        return jobs_for_worker(conn, worker_url)
    return find_jobs(conn, status)


def held_job(conn, id, worker_url):
    job = get_job(conn, id)
    if job is None:
        raise NoSuchJob(id)
    if job.worker_url != worker_url:
        raise NotHeld(id)
    return job


def claim_job(conn, root, id, worker_url):
    """The job's payload (with its closure) if claimed, else None"""
    if not claim(conn, id, worker_url):
        return None
    job = get_job(conn, id)
    run = store.load_run(root, job.report_id, job.id)
    return {
        **job_json(job),
        "load_order": run.get("load_order", [job.script]),
        "imports": run.get("imports", []),
        "closure": store.read_closure(root, job.report_id, job.id),
    }


def start_job(conn, root, id, worker_url):
    job = held_job(conn, id, worker_url)
    start(conn, id, worker_url)
    store.update_run(root, job.report_id, job.id, started=store.now_iso())


def release_job(conn, root, id, worker_url):
    """Give a job back to the queue and forget the probe that ran it"""
    job = held_job(conn, id, worker_url)
    release(conn, id, worker_url)
    store.reset_run(root, job.report_id, job.id)


def record_events(conn, root, id, worker_url, events):
    job = held_job(conn, id, worker_url)
    store.append_events(root, job.report_id, job.id, events)


def complete_job(conn, root, id, worker_url, outcome, installed=None,
                 fingerprint=None, mode=None):
    """Record the outcome, and what the worker actually ran against"""
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {OUTCOMES}")
    job = held_job(conn, id, worker_url)
    details = {"installed": installed, "fingerprint": fingerprint, "mode": mode}
    finish(conn, root, job, outcome,
           **{key: value for key, value in details.items() if value is not None})
