"""Queue pages and the job API workers call over HTTP

The API is a thin HTTP adapter over services.jobs; workers can equally
use those functions in-process (services.worker.local).
"""

import base64
from dataclasses import asdict
from datetime import datetime

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

from ..framework.planning import build_plan
from ..services import jobs as models
from ..services.reports import store
from ..services.requirements import links
from ..services.workspace import find_worktrees
from .db import get_db

jobqueue = Blueprint("jobqueue", __name__)


def reports_root():
    return current_app.config["REPORTS_PATH"]


def workspace_root(name):
    """The rvts root of the worktree for branch `name`, or None"""
    if not name:
        return None
    return find_worktrees(current_app.config["WORKSPACE_PATH"]).get(name)


@jobqueue.route("/", methods=["GET"])
def list():
    conn = get_db()
    models.reap_lost_jobs(conn, reports_root())
    return render_template("queue.html", jobs=models.find_jobs(conn))


# Pages


def live_environments():
    since = datetime.utcnow() - models.MISSING_AFTER
    live = {}
    for worker in models.find_workers(get_db(), since=since):
        for name in worker.environments:
            live.setdefault(name, []).append(worker.url)
    return live


def target_report(args):
    """The report a queue dialog adds to (its `report` argument), or None
    for a new one"""
    report_id = args.get("report")
    if not report_id:
        return None
    return store.load_report(reports_root(), report_id) or abort(404)


def plan_from(args):
    """The plan for a queue dialog request (query string or form). Adding
    to a report uses its workspace, defaults to its UUT versions and
    leaves out combinations that already passed there."""
    report = target_report(args)
    workspace = report["workspace"] if report else args.get("workspace", "")
    root = workspace_root(workspace)
    if root is None:
        abort(404)
    conn = get_db()
    links.refresh(conn, workspace, root)

    versions = {uut: v["id"] for uut, v in (report or {}).get("uut_versions", {}).items()}
    versions.update({
        key[len("version-"):]: value
        for key, value in args.items()
        if key.startswith("version-") and value
    })
    configured = args.get("configured") == "1"
    options = dict(
        scripts=args.getlist("script"),
        requirements=args.getlist("requirement"),
        versions=versions,
        variations=set(args.getlist("variation")) if configured else None,
        filter_source=args.get("filter", ""),
        links=links.scripts_by_requirement(conn, workspace),
        passed=models.passed_combinations(reports_root(), report["id"]) if report else None,
        rerun_passed=set(args.getlist("rerun")),
    )
    environments = args.getlist("environment") if configured else None
    plan = build_plan(workspace, root, environments=environments, **options)
    if not configured:
        # Default to the environments some live worker offers
        live = [e for e in plan.available_environments if e in live_environments()]
        if live and live != plan.environments:
            plan = build_plan(workspace, root, environments=live, **options)
    return plan


def render_dialog(plan, report=None, errors=()):
    template = "queue_new.html"
    if request.headers.get("HX-Request"):
        template = "partials/queue_form.html"
    return render_template(
        template,
        plan=plan,
        report=report,
        runs=plan.runs(),
        live=live_environments(),
        errors=[*errors, *plan.errors],
    )


@jobqueue.route("/new", methods=["GET"])
def new():
    """Queue dialog: choose environments, versions and variations"""
    return render_dialog(plan_from(request.args), target_report(request.args))


@jobqueue.route("/queue", methods=["POST"])
def queue():
    """Queue the dialog's selection as a new report, or add it to the
    report it targets: requirements added there are tracked, tests added
    on their own are not"""
    plan = plan_from(request.form)
    report = target_report(request.form)
    try:
        if report is None:
            report_id, _ = models.queue_plan(get_db(), reports_root(), plan)
        else:
            report_id = report["id"]
            tracked = plan.requirements if request.form.getlist("requirement") else {}
            models.add_plan(get_db(), reports_root(), report_id, plan, tracked)
    except models.QueueError as e:
        return render_dialog(plan, report, e.errors)
    target = url_for("reports.report", report_id=report_id)
    if request.headers.get("HX-Request"):
        resp = make_response("", 204)
        resp.headers["HX-Redirect"] = target
        return resp
    return redirect(target)


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


# Worker API


def worker_url():
    return (request.json or {}).get("worker_url")


def api_call(operation, *args, **kwargs):
    """Run a services.jobs operation, mapping its errors to HTTP"""
    try:
        return operation(get_db(), reports_root(), *args, **kwargs), None
    except models.NoSuchJob:
        return None, (jsonify({"error": "No such job"}), 404)
    except models.NotHeld:
        return None, (jsonify({"error": "Job is not held by this worker"}), 409)
    except ValueError as e:
        return None, (jsonify({"error": str(e)}), 400)


@jobqueue.route("/workers", methods=["POST"])
def register_worker():
    data = request.json or {}
    if not data.get("url"):
        return jsonify({"error": "Worker name is required"}), 400
    _, error = api_call(
        models.check_in,
        data["url"],
        data.get("status", "available"),
        uut_types=data.get("uut_types"),
        environments=data.get("environments"),
        started=bool(data.get("started")),
    )
    return error or ("OK!", 200)


@jobqueue.route("/jobs", methods=["GET"])
def list_jobs():
    jobs = models.available_jobs(
        get_db(),
        reports_root(),
        request.args.get("worker_url"),
        request.args.get("status", "pending"),
    )
    return jsonify([models.job_json(job) for job in jobs])


@jobqueue.route("/jobs/<id>/claim", methods=["POST"])
def claim_job(id):
    if not worker_url():
        return jsonify({"error": "worker_url is required"}), 400
    job, _ = api_call(models.claim_job, id, worker_url())
    if job is None:
        return jsonify({"error": "Job is not pending"}), 409
    return jsonify(job)


@jobqueue.route("/jobs/<id>/start", methods=["POST"])
def start_job(id):
    _, error = api_call(models.start_job, id, worker_url())
    return error or jsonify({"status": "running"})


@jobqueue.route("/jobs/<id>/release", methods=["POST"])
def release_job(id):
    _, error = api_call(models.release_job, id, worker_url())
    return error or jsonify({"status": "pending"})


@jobqueue.route("/jobs/<id>/events", methods=["POST"])
def post_events(id):
    _, error = api_call(models.record_events, id, worker_url(), request.json["events"])
    return error or jsonify({"status": "ok"})


@jobqueue.route("/jobs/<id>/files", methods=["POST"])
def attach_file(id):
    """JSON body: worker_url, name, data (base64)"""
    data = request.json or {}
    try:
        content = base64.b64decode(data.get("data", ""), validate=True)
    except ValueError:
        return jsonify({"error": "data must be base64"}), 400
    name, error = api_call(models.attach_file, id, worker_url(),
                           data.get("name", ""), content)
    return error or jsonify({"name": name})


@jobqueue.route("/jobs/<id>/complete", methods=["POST"])
def complete_job(id):
    data = request.json or {}
    outcome = data.get("outcome")
    _, error = api_call(
        models.complete_job,
        id,
        worker_url(),
        outcome,
        **{key: data[key]
           for key in ("installed", "fingerprint", "mode") if key in data},
    )
    return error or jsonify({"status": "done", "outcome": outcome})


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
