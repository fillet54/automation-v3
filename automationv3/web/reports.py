"""Report and run pages, rendered from the filesystem store"""

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)

from ..framework.closure import DIRECTIVES, PRECONDITION, head
from ..framework.testcase import get_statements
from ..services import jobs as models
from ..services.reports import rollup, store
from ..services.requirements import models as requirement_models
from .db import get_db

reports = Blueprint("reports", __name__)


def root():
    return current_app.config["REPORTS_PATH"]


def run_status(run):
    """The outcome of a finished run, else its job's queue status"""
    if run.get("outcome"):
        return run["outcome"]
    job = models.get_job(get_db(), run["id"])
    return job.status if job else "unknown"


def statement_rows(run, finished):
    """The rendered script, each statement paired with its step result"""
    closure = store.read_closure(root(), run["report_id"], run["id"])
    text = closure.get(run["script"], "")
    events = store.read_events(root(), run["report_id"], run["id"])

    started = {e["index"] for e in events if e["kind"] == "step_start"}
    ended = {e["index"]: e for e in events if e["kind"] == "step_end"}

    rows = []
    for index, statement in enumerate(get_statements(text)):
        form = statement.statement
        row = {
            "html": statement.html,
            "step": isinstance(form, list) and head(form) not in DIRECTIVES,
            "precondition": head(form) == PRECONDITION,
        }
        if row["step"]:
            if index in ended:
                row["state"] = "pass" if ended[index]["passed"] else "fail"
                row["result"] = ended[index]
            elif index in started:
                row["state"] = "running"
            else:
                row["state"] = "not run" if finished else "pending"
        rows.append(row)

    errors = [e for e in events if e["kind"] == "error"]
    return rows, errors


@reports.route("/", methods=["GET"])
def index():
    all_reports = [
        {**report, "runs": store.list_runs(root(), report["id"])}
        for report in store.list_reports(root())
    ]
    return render_template("reports/reports.html", reports=all_reports)


@reports.route("/<report_id>", methods=["GET"])
def report(report_id):
    report = store.load_report(root(), report_id) or abort(404)
    runs = store.list_runs(root(), report_id)
    for run in runs:
        run["status"] = run_status(run)

    rows = rollup.combinations(report, runs, lambda run: run["status"])
    requirements = rollup.requirement_rollup(report, rows)
    texts = {
        r.id: r.text
        for r in (requirement_models.find_by_id(get_db(), req["id"])
                  for req in requirements)
        if r is not None
    }
    skipped = [
        s for s in report.get("scripts", []) if isinstance(s, dict) and s["skipped"]
    ]
    in_progress = any(run.get("outcome") is None for run in runs)

    template = "reports/report.html"
    if request.headers.get("HX-Request"):
        template = "reports/partials/report_body.html"
    return render_template(
        template,
        report=report,
        rows=rows,
        requirements=requirements,
        texts=texts,
        skipped=skipped,
        in_progress=in_progress,
    )


@reports.route("/<report_id>/runs/<run_id>", methods=["GET"])
def run(report_id, run_id):
    run = store.load_run(root(), report_id, run_id) or abort(404)
    status = run_status(run)
    finished = run.get("outcome") is not None
    rows, errors = statement_rows(run, finished)

    template = "reports/run.html"
    if request.headers.get("HX-Request"):
        template = "reports/partials/run_body.html"
    return render_template(
        template, run=run, status=status, finished=finished, rows=rows, errors=errors
    )


@reports.route("/<report_id>/runs/<run_id>/rerun", methods=["POST"])
def rerun(report_id, run_id):
    """Queue the same closure, environment and versions as a new run"""
    store.load_run(root(), report_id, run_id) or abort(404)
    new_id = models.rerun(get_db(), root(), report_id, run_id)
    return redirect(url_for("reports.run", report_id=report_id, run_id=new_id))
