"""Report and run pages, rendered from the filesystem store"""

from collections import defaultdict
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)

from . import store
from ..database import get_db
from ..framework.testcase import get_statements
from ..jobqueue import models

reports = Blueprint(
    "reports", __name__, template_folder=Path(__file__).resolve().parent / "templates"
)


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
        row = {"html": statement.html, "step": isinstance(statement.statement, list)}
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

    # Latest run per script, earlier runs listed as reruns
    by_script = defaultdict(list)
    for run in store.list_runs(root(), report_id):
        run["status"] = run_status(run)
        by_script[run["script"]].append(run)
    scripts = [
        {"script": script, "latest": runs[-1], "earlier": runs[-2::-1]}
        for script, runs in sorted(by_script.items())
    ]
    return render_template("reports/report.html", report=report, scripts=scripts)


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
    """Queue the same closure again as a new run in the same report"""
    run = store.load_run(root(), report_id, run_id) or abort(404)
    closure = store.read_closure(root(), report_id, run_id)
    new_id = models.enqueue(get_db(), root(), report_id, run["script"], closure)
    return redirect(url_for("reports.run", report_id=report_id, run_id=new_id))
