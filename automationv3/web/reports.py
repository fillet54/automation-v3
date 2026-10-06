"""Report and run pages, rendered from the filesystem store"""

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    send_file,
    request,
    url_for,
)

from dataclasses import asdict

from ..framework.language import DIRECTIVES, head
from ..framework.statements import get_statements
from ..framework.uut import uut_types
from ..services import jobs as models
from ..services.reports import rollup, store
from ..services.requirements import models as requirement_models
from ..services.workspace import find_worktrees
from .db import get_db
from .grouping import group, statement_item

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
    """The rendered script, each statement paired with its step result.
    Statements limited to variations other than the run's are left out."""
    closure = store.read_closure(root(), run["report_id"], run["id"])
    text = closure.get(run["script"], "")
    events = store.read_events(root(), run["report_id"], run["id"])

    started = {e["index"] for e in events if e["kind"] == "step_start"}
    ended = {e["index"]: e for e in events if e["kind"] == "step_end"}
    calls = call_trees(events)
    phases = precondition_phases(events, calls)
    attachments = {}
    for event in events:
        if event["kind"] == "attachment":
            attachments.setdefault(event.get("index"), []).append(event)
    variation = (run.get("variation") or {}).get("name")

    rows = []
    for index, statement in enumerate(get_statements(text)):
        if variation and statement.variations and variation not in statement.variations:
            continue  # limited to other variations: not part of this run
        form = statement.statement
        row = statement_item(
            statement,
            step=isinstance(form, list) and head(form) not in DIRECTIVES,
            calls=calls.get(index, []),
            phases=phases.get(index, []),
            attachments=attachments.get(index, []),
        )
        if statement.definition:
            # Definitions aren't steps; only a failed one has a result
            row["step"] = index in ended
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
    return group(rows, variation), errors


@reports.app_template_filter()
def flatten(fingerprint):
    """A fingerprint's (dotted key, value) pairs, sorted"""
    return sorted(models.flatten(fingerprint).items())


@reports.app_template_filter()
def duration(seconds):
    """A step's duration to the millisecond: 7 ms, 1.234 s, 2:05.012"""
    if seconds is None:
        return ""
    ms = round(seconds * 1000)
    if ms < 1000:
        return f"{ms} ms"
    if ms < 60_000:
        return f"{ms / 1000:.3f} s"
    minutes, ms = divmod(ms, 60_000)
    return f"{minutes}:{ms / 1000:06.3f}"


def precondition_phases(events, calls):
    """statement index -> the phases its precondition ran (check, heal,
    check again), in order: each has its action, state, result and the
    block calls made in it"""
    phases = {}
    for event in events:
        if event["kind"] in ("phase_start", "phase_end"):
            phase = phases.setdefault((event["index"], event["phase"]), {})
            phase.update({k: v for k, v in event.items()
                          if k not in ("kind", "seq", "ts")})
            if event["kind"] == "phase_end":
                phase["result"] = event
    by_index = {}
    for (index, number), phase in sorted(phases.items()):
        phase["state"] = phase_state(phase)
        phase["calls"] = [c for c in calls.get(index, []) if c.get("phase") == number]
        by_index.setdefault(index, []).append(phase)
    return by_index


def phase_state(phase):
    """A check is true or false (false is expected before a heal); a heal
    passes or fails"""
    if "result" not in phase:
        return "running"
    if phase["action"] == "check":
        return "true" if phase["passed"] else "false"
    return "pass" if phase["passed"] else "fail"


def call_state(call):
    if "passed" not in call:
        return "running"
    if call.get("checked"):
        return "true" if call["passed"] else "false"
    return "pass" if call["passed"] else "fail"


def call_trees(events):
    """statement index -> its block calls as a tree, quiet calls left out.

    Each call has its `children` (calls nested in a defblock call) and a
    `nested` flag for calls the statement's own defblock nested.
    """
    calls = {}
    for event in events:
        if event["kind"] not in ("call_start", "call_end") or event.get("quiet"):
            continue
        call = calls.setdefault((event["index"], event["call"]), {"children": []})
        call.update({k: v for k, v in event.items() if k not in ("kind", "seq", "ts")})
    for call in calls.values():
        call["state"] = call_state(call)

    trees = {}
    for (index, _), call in sorted(calls.items()):
        parent = calls.get((index, call.get("parent")))
        if parent is not None:
            parent["children"].append(call)
        else:
            trees.setdefault(index, []).append(call)
    return trees


@reports.route("/", methods=["GET"])
def index():
    all_reports = [
        {**report, "runs": store.list_runs(root(), report["id"])}
        for report in store.list_reports(root())
    ]
    return render_template("reports/reports.html", reports=all_reports)


def uut_choices():
    """UUT name -> version ids, newest first, for every UUT plugin"""
    return {name: [v.id for v in reversed(cls().list_versions())]
            for name, cls in sorted(uut_types().items())}


@reports.route("/new", methods=["GET", "POST"])
def new():
    """Create an empty report for one build: a name, a workspace and one
    version per UUT type"""
    workspaces = sorted(find_worktrees(current_app.config["WORKSPACE_PATH"]))
    choices = uut_choices()
    errors = []
    if request.method == "POST":
        form = request.form
        name = form.get("name", "").strip()
        workspace = form.get("workspace")
        versions = {}
        for uut, cls in uut_types().items():
            version = cls().find_version(form.get(f"version-{uut}", ""))
            if version is not None:
                versions[uut] = asdict(version)
        if not name:
            errors.append("A report needs a name")
        if workspace not in workspaces:
            errors.append("Pick a workspace")
        if not errors:
            report_id = models.create_report(root(), workspace, name, versions)
            return redirect(url_for("reports.report", report_id=report_id))
    return render_template("reports/new.html", workspaces=workspaces, choices=choices,
                           form=request.form, errors=errors)


def version_mix(report, runs):
    """uut -> {version id: runs} for runs using a version other than the
    report's"""
    defaults = {uut: v["id"] for uut, v in (report.get("uut_versions") or {}).items()}
    mix = {}
    for run in runs:
        for uut, version in (run.get("uut_versions") or {}).items():
            if version["id"] != defaults.get(uut):
                counts = mix.setdefault(uut, {})
                counts[version["id"]] = counts.get(version["id"], 0) + 1
    return mix


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
        mix=version_mix(report, runs),
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
    files = store.list_files(root(), report_id, run_id)
    return render_template(template, run=run, status=status, finished=finished,
                           rows=rows, errors=errors, files=files)


@reports.route("/<report_id>/runs/<run_id>/files/<name>", methods=["GET"])
def run_file(report_id, run_id, name):
    """A file attached to the run"""
    path = store.file_path(root(), report_id, run_id, name) or abort(404)
    return send_file(path)


@reports.route("/<report_id>/runs/<run_id>/rerun", methods=["POST"])
def rerun(report_id, run_id):
    """Queue the same closure, environment and versions as a new run; if
    the environment drifted, show how (unless forced)"""
    run = store.load_run(root(), report_id, run_id) or abort(404)
    force = request.form.get("force") == "1"
    try:
        new_id = models.rerun(get_db(), root(), report_id, run_id, force=force)
    except models.Drift as drift:
        return render_template("reports/drift.html", run=run, drift=drift), 409
    return redirect(url_for("reports.run", report_id=report_id, run_id=new_id))
