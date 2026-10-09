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
    fingerprint_hash: str = None  # a CM rerun's: only matching workers run it


def _job(row):
    (id, report_id, script, environment, variation, uut_versions,
     status, worker_url, queued_at, claimed_at, fingerprint_hash) = row
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
        fingerprint_hash,
    )


JOB_COLUMNS = (
    "id, report_id, script, environment, variation, uut_versions, "
    "status, worker_url, queued_at, claimed_at, fingerprint_hash"
)


class QueueError(Exception):
    """A request that can't be queued, with every reason why"""

    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def enqueue(conn, root, report_id, script, files, load_order,
            environment=None, uut_versions=None, imports=(), variation=None,
            fingerprint_hash=None, **run_fields):
    """Create a run folder in the report and queue it as a job.

    `variation` is None or {"name", "values"} (values as edn text).
    `fingerprint_hash` pins the job to workers whose environment has that
    fingerprint; `run_fields` are recorded in run.json as they are.
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
        **run_fields,
    )
    with conn:
        conn.execute(
            """
            INSERT INTO jobs(id, report_id, script, environment, variation,
                             uut_versions, fingerprint_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                report_id,
                script,
                environment,
                variation["name"] if variation else None,
                json.dumps(uut_versions),
                fingerprint_hash,
            ),
        )
    return run_id


def closure_hash(files, load_order):
    return Closure(load_order[-1], files, load_order).hash


def create_report(root, workspace, name="", uut_versions=None):
    """An empty report for one workspace. Its UUT versions (name ->
    {id, digest}) are the default for every addition."""
    return store.create_report(root, name=name, workspace=workspace,
                               uut_versions=uut_versions or {}, requirements={},
                               scripts=[], additions=[])


def check_runnable(plan):
    """Raise QueueError if the plan has errors or nothing to run"""
    if plan.errors or not plan.runs():
        errors = list(plan.errors) or ["Nothing to run"]
        errors += [f"{s.script}: {s.skipped}" for s in plan.scripts if s.skipped]
        raise QueueError(errors)


def add_plan(conn, root, report_id, plan, requirements=None):
    """Queue every run of `plan` in an existing report. `requirements`
    (id -> linked scripts) join the report's tracked requirements.

    Returns the run ids. Raises QueueError if nothing can run.
    """
    check_runnable(plan)
    runs = plan.runs()
    report = store.load_report(root, report_id)
    summary = plan.summary()
    store.update_report(
        root,
        report_id,
        requirements={**report.get("requirements", {}), **(requirements or {})},
        scripts=merge_scripts(report.get("scripts", []), summary["scripts"]),
        additions=[*report.get("additions", []), {
            "added": store.now_iso(),
            "requirements": sorted(requirements or {}),
            "scripts": [s.script for s in plan.scripts],
            "environments": plan.environments,
            "uut_versions": plan.uut_versions,
            "filter": plan.filter,
            "runs": len(runs),
        }],
    )

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
    return run_ids


def merge_scripts(entries, added):
    """A report's script entries with an addition's merged in: a script
    added again keeps every combination it was expected to cover"""
    merged = {entry["script"]: entry for entry in entries if isinstance(entry, dict)}
    for entry in added:
        before = merged.get(entry["script"], {})
        expected = list(before.get("expected", []))
        expected += [combo for combo in entry["expected"] if combo not in expected]
        requirements = sorted({*before.get("requirements", []), *entry["requirements"]})
        merged[entry["script"]] = {**entry, "expected": expected,
                                   "requirements": requirements}
    return list(merged.values())


def queue_plan(conn, root, plan, name=None):
    """Queue every run of `plan` under one new report, tracking the
    requirements it covers: the one-step path from a selection.

    Returns (report_id, run_ids). Raises QueueError if the plan has
    errors or nothing to run.
    """
    check_runnable(plan)
    report_id = create_report(root, plan.workspace, name or default_name(plan),
                              plan.uut_versions)
    return report_id, add_plan(conn, root, report_id, plan, plan.requirements)


def default_name(plan):
    """What a report queued in one step covers, e.g. "R1, R2 and 3 more" """
    names = list(plan.requirements) or [s.script.split("/")[-1] for s in plan.scripts]
    if len(names) > 3:
        return f"{', '.join(names[:2])} and {len(names) - 2} more"
    return ", ".join(names)


def reports_for(root, workspace):
    """Reports of `workspace` a selection can be added to, newest first"""
    if not root or not workspace:
        return []
    return [r for r in store.list_reports(root) if r.get("workspace") == workspace]


def passed_combinations(root, report_id):
    """(script, environment, variation) whose latest run in the report
    passed"""
    latest = {}
    for run in store.list_runs(root, report_id):  # oldest first
        variation = (run.get("variation") or {}).get("name")
        latest[(run["script"], run.get("environment"), variation)] = run
    return {key for key, run in latest.items() if run.get("outcome") == "pass"}


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


class Drift(Exception):
    """No live worker offers the run's environment with its fingerprint.

    `diffs` maps each live worker offering the environment to how its
    fingerprint differs: [(key, then, now)].
    """

    def __init__(self, environment, diffs):
        super().__init__(f"No live worker offers {environment} as it was")
        self.environment = environment
        self.diffs = diffs


def rerun(conn, root, report_id, run_id, force=False):
    """Queue the run again, exactly: the same closure, environment,
    variation and UUT versions, as a new run in the same report.

    A run that recorded its environment's fingerprint is rerun only on
    a worker whose environment still has it; if no live worker does,
    Drift is raised. `force` queues it anyway, marked non_identical.
    """
    run = store.load_run(root, report_id, run_id)
    files = store.read_closure(root, report_id, run_id)
    pin, extra = None, {"rerun_of": run_id}
    if run.get("fingerprint") is not None:
        live = live_fingerprints(conn, run.get("environment"))
        if run["fingerprint_hash"] in {fingerprint_hash(fp) for fp in live.values()}:
            pin = run["fingerprint_hash"]
        elif force:
            extra["non_identical"] = True
        else:
            raise Drift(run.get("environment"), {
                url: fingerprint_diff(run["fingerprint"], fingerprint)
                for url, fingerprint in live.items()
            })
    return enqueue(conn, root, report_id, run["script"], files,
                   run.get("load_order", [run["script"]]),
                   run.get("environment"), run.get("uut_versions"),
                   run.get("imports", []), run.get("variation"),
                   fingerprint_hash=pin, **extra)


def live_fingerprints(conn, environment):
    """worker url -> current fingerprint, for live workers offering
    `environment`"""
    since = datetime.utcnow() - MISSING_AFTER
    return {
        worker.url: worker.environments[environment]
        for worker in find_workers(conn, since=since)
        if environment in worker.environments
    }


def fingerprint_diff(then, now):
    """[(key, value then, value now)] for every key that differs; nested
    keys are dotted (framework.git)"""
    then, now = flatten(then), flatten(now)
    return [(key, then.get(key), now.get(key))
            for key in sorted(then.keys() | now.keys())
            if then.get(key) != now.get(key)]


def flatten(value, prefix=""):
    """A nested dict as {dotted key: value}"""
    if not isinstance(value, dict):
        return {prefix: value}
    flat = {}
    for key, item in value.items():
        nested = isinstance(item, dict)
        flat.update(flatten(item, f"{prefix}{key}." if nested else f"{prefix}{key}"))
    return flat


def identity_hash(run):
    """What makes two runs the same test: the closure, the variation's
    values, the UUT versions and digests and the environment's fingerprint"""
    variation = run.get("variation") or {}
    identity = {
        "closure": run.get("closure_hash"),
        "variation": variation.get("values"),
        "uut_versions": {name: {"id": v["id"], "digest": v["digest"]}
                         for name, v in (run.get("uut_versions") or {}).items()},
        "fingerprint": run.get("fingerprint_hash"),
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


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
        and (job.fingerprint_hash is None or job.fingerprint_hash
             == fingerprint_hash(worker.environments[job.environment]))
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

OUTCOMES = ["pass", "fail", "blocked", "error", "incomplete"]


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


def attach_file(conn, root, id, worker_url, name, data):
    """Store a file with the job's run. Returns the name it was stored as."""
    job = held_job(conn, id, worker_url)
    return store.save_file(root, job.report_id, job.id, name, data)


def complete_job(conn, root, id, worker_url, outcome, installed=None,
                 fingerprint=None, mode=None):
    """Record the outcome, and what the worker actually ran against"""
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {OUTCOMES}")
    job = held_job(conn, id, worker_url)
    details = {"installed": installed, "fingerprint": fingerprint, "mode": mode}
    if fingerprint is not None:
        details["fingerprint_hash"] = fingerprint_hash(fingerprint)
    run = store.load_run(root, job.report_id, job.id)
    details["identity"] = identity_hash({**run, **details})
    finish(conn, root, job, outcome,
           **{key: value for key, value in details.items() if value is not None})


# The scratch space: runs of scripts under development. They live in the
# reserved `scratch` folder of the reports root, which has no
# report.json, so they never appear in a report or a rollup. They run
# the workspace's files as they are on disk, uncommitted changes
# included, and can be cleared.

SCRATCH = "scratch"


def queue_scratch(conn, root, plan):
    """Queue every run of `plan` in the scratch space. Returns the run ids."""
    check_runnable(plan)
    run_ids = []
    for script_plan, environment, variation in plan.runs():
        closure = script_plan.closure
        if variation is not None:
            choice = next(v for v in script_plan.variations if v.name == variation)
            variation = {"name": choice.name, "values": choice.values}
        run_ids.append(enqueue(
            conn, root, SCRATCH, closure.script, closure.files, closure.load_order,
            environment, {name: plan.uut_versions[name] for name in closure.uuts},
            closure.imports, variation, workspace=plan.workspace,
        ))
    return run_ids


def scratch_runs(root):
    """Scratch runs, newest first"""
    return list(reversed(store.list_runs(root, SCRATCH)))


def run_again(conn, root, workspace_root, run_id):
    """Queue a scratch run again with the script as it is now: the same
    script, environment, variation and UUT versions. Returns the run id."""
    run = store.load_run(root, SCRATCH, run_id)
    variation = (run.get("variation") or {}).get("name")
    plan = build_plan(
        run.get("workspace", ""),
        workspace_root,
        [run["script"]],
        environments=[run["environment"]] if run.get("environment") else None,
        versions={uut: v["id"] for uut, v in (run.get("uut_versions") or {}).items()},
        variations={f"{run['script']}::{variation}"} if variation else None,
    )
    (run_id,) = queue_scratch(conn, root, plan)
    return run_id


def clear_scratch(root):
    """Delete the finished scratch runs; queued and running ones stay.
    Returns how many were deleted."""
    finished = [run for run in store.list_runs(root, SCRATCH) if run.get("outcome")]
    for run in finished:
        store.delete_run(root, SCRATCH, run["id"])
    return len(finished)
