"""Job Runner / Queue

Workers pull work: they list pending jobs, atomically claim one, stream
its events back and complete it with an outcome. Every call that acts on
a job carries the worker's url, and only the worker holding a job may
act on it.
"""

from pathlib import Path
from flask import Blueprint, current_app, render_template, request, jsonify
from dataclasses import asdict
from datetime import datetime

from . import models
from ..database import get_db
from ..reports import store

jobqueue = Blueprint(
    "jobqueue", __name__, template_folder=Path(__file__).resolve().parent / "templates"
)

OUTCOMES = ["pass", "fail", "error"]


def reports_root():
    return current_app.config["REPORTS_PATH"]


def job_json(job):
    return {
        **asdict(job),
        "queued_at": str(job.queued_at),
        "claimed_at": str(job.claimed_at),
    }


@jobqueue.route("/", methods=["GET"])
def list():
    conn = get_db()
    models.reap_lost_jobs(conn, reports_root())
    return render_template("queue.html", jobs=models.find_jobs(conn))


@jobqueue.route("/workers", methods=["POST"])
def register_worker():
    data = request.json
    worker_url = data.get("url")  # TODO: Validate url
    worker_status = data.get("status", "available")

    if not worker_url:
        return jsonify({"error": "Worker name is required"}), 400
    if worker_status not in models.ALLOWED_STATUS:
        return jsonify({"error": f"Status must be one of {models.ALLOWED_STATUS}"}), 400

    conn = get_db()
    models.save_worker(
        conn,
        worker_url,
        worker_status,
        uut_types=data.get("uut_types"),
        environments=data.get("environments"),
    )

    # A (re)starting worker can't still be running anything it held before
    if data.get("started"):
        models.fail_worker_jobs(
            conn, reports_root(), worker_url, f"Worker {worker_url} restarted"
        )

    return "OK!", 200


@jobqueue.route("/jobs", methods=["GET"])
def list_jobs():
    conn = get_db()
    models.reap_lost_jobs(conn, reports_root())
    if "worker_url" in request.args:
        jobs = models.jobs_for_worker(conn, request.args["worker_url"])
    else:
        jobs = models.find_jobs(conn, request.args.get("status", "pending"))
    return jsonify([job_json(job) for job in jobs])


@jobqueue.route("/jobs", methods=["POST"])
def queue_job():
    """Queue a script as a new report.

    JSON body: workspace (branch name), script (path relative to its rvts
    root), and optionally text (content overriding the file), environment
    and uut_versions (uut name -> version id).
    """
    data = request.json or {}
    root = workspace_root(data.get("workspace"))
    if root is None or not data.get("script"):
        return jsonify({"errors": ["a known workspace and a script are required"]}), 400
    try:
        report_id, run_id = models.queue_script(
            get_db(),
            reports_root(),
            root,
            data["script"],
            text=data.get("text"),
            environment=data.get("environment"),
            versions=data.get("uut_versions"),
        )
    except models.QueueError as e:
        return jsonify({"errors": e.errors}), 400
    except FileNotFoundError:
        return jsonify({"errors": [f"No script {data['script']}"]}), 400
    return jsonify({"report_id": report_id, "run_id": run_id}), 201


def workspace_root(name):
    """The rvts root of the worktree for branch `name`, or None"""
    from ..editor.workspace import find_worktrees

    if not name:
        return None
    return find_worktrees(current_app.config["WORKSPACE_PATH"]).get(name)


def held_job(id):
    """The job `id` if the requesting worker holds it, else an error response"""
    worker_url = (request.json or {}).get("worker_url")
    job = models.get_job(get_db(), id)
    if job is None:
        return None, (jsonify({"error": "No such job"}), 404)
    if job.worker_url != worker_url:
        return None, (jsonify({"error": "Job is not held by this worker"}), 409)
    return job, None


@jobqueue.route("/jobs/<id>/claim", methods=["POST"])
def claim_job(id):
    worker_url = (request.json or {}).get("worker_url")
    if not worker_url:
        return jsonify({"error": "worker_url is required"}), 400

    conn = get_db()
    if not models.claim(conn, id, worker_url):
        return jsonify({"error": "Job is not pending"}), 409

    job = models.get_job(conn, id)
    run = store.load_run(reports_root(), job.report_id, job.id)
    return jsonify(
        {
            **job_json(job),
            "load_order": run.get("load_order", [job.script]),
            "imports": run.get("imports", []),
            "closure": store.read_closure(reports_root(), job.report_id, job.id),
        }
    )


@jobqueue.route("/jobs/<id>/start", methods=["POST"])
def start_job(id):
    job, error = held_job(id)
    if error:
        return error
    models.start(get_db(), id, job.worker_url)
    store.update_run(reports_root(), job.report_id, job.id, started=store.now_iso())
    return jsonify({"status": "running"})


@jobqueue.route("/jobs/<id>/release", methods=["POST"])
def release_job(id):
    job, error = held_job(id)
    if error:
        return error
    models.release(get_db(), id, job.worker_url)
    return jsonify({"status": "pending"})


@jobqueue.route("/jobs/<id>/events", methods=["POST"])
def post_events(id):
    job, error = held_job(id)
    if error:
        return error
    store.append_events(reports_root(), job.report_id, job.id, request.json["events"])
    return jsonify({"status": "ok"})


@jobqueue.route("/jobs/<id>/complete", methods=["POST"])
def complete_job(id):
    job, error = held_job(id)
    if error:
        return error
    outcome = request.json.get("outcome")
    if outcome not in OUTCOMES:
        return jsonify({"error": f"outcome must be one of {OUTCOMES}"}), 400
    # What the worker actually ran against, kept for configuration management
    extra = {
        key: request.json[key]
        for key in ("installed", "fingerprint")
        if key in request.json
    }
    models.finish(get_db(), reports_root(), job, outcome, **extra)
    return jsonify({"status": "done", "outcome": outcome})


@jobqueue.route("/workers", methods=["GET"])
def list_workers():
    show = request.args.get("show")
    show_all = show and show == "all"
    hx_request = request.headers.get("HX-Request", False)

    now = datetime.utcnow()
    missing_time = now - models.MISSING_AFTER

    workers = models.find_workers(get_db(), None if show_all else missing_time)

    if hx_request or "text/html" in request.headers.get("Accept", ""):
        return render_template(
            "workers.html",
            workers=workers,
            show_all=(None if show_all else "all"),
            missing_time=missing_time,
            hx_request=request.headers.get("HX-Request", False),
        )
    else:
        return jsonify([asdict(worker) for worker in workers])


@jobqueue.app_template_filter()
def humanize_ts(timestamp=False):
    """
    Get a datetime object or a int() Epoch timestamp and return a
    pretty string like 'an hour ago', 'Yesterday', '3 months ago',
    'just now', etc
    """
    now = datetime.utcnow()
    try:
        diff = now - timestamp
    except TypeError:
        diff = now - datetime.fromtimestamp(timestamp)
    second_diff = diff.seconds
    day_diff = diff.days

    if day_diff < 0:
        return ""

    if day_diff == 0:
        if second_diff < 10:
            return "just now"
        if second_diff < 60:
            return str(int(second_diff)) + " seconds ago"
        if second_diff < 120:
            return "a minute ago"
        if second_diff < 3600:
            return str(int(second_diff / 60)) + " minutes ago"
        if second_diff < 7200:
            return "an hour ago"
        if second_diff < 86400:
            return str(int(second_diff / 3600)) + " hours ago"
    if day_diff == 1:
        return "Yesterday"
    if day_diff < 7:
        return str(day_diff) + " days ago"
    if day_diff < 31:
        return str(int(day_diff / 7)) + " weeks ago"
    if day_diff < 365:
        return str(int(day_diff / 30)) + " months ago"
    return str(int(day_diff / 365)) + " years ago"
