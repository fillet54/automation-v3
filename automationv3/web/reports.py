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

from dataclasses import asdict, dataclass

from ..framework.excerpt import failure_view
from ..framework.language import DIRECTIVES, head
from ..framework.statements import get_statements
from ..framework.uut import uut_types
from ..services import jobs as models
from ..services.reports import rollup, store
from ..services.requirements import models as requirement_models
from ..services.workspace import find_worktrees
from .db import get_db
from .grouping import STATE_ORDER, group, statement_item

reports = Blueprint("reports", __name__)


def root():
    return current_app.config["REPORTS_PATH"]


def run_status(run):
    """The outcome of a finished run, else its job's queue status"""
    if run.get("outcome"):
        return run["outcome"]
    job = models.get_job(get_db(), run["id"])
    return job.status if job else "unknown"


def key(event):
    """A step's events are keyed by its statement index, and its row when
    it ran in a table block"""
    return (event.get("index"), event.get("row"))


def statement_rows(run, finished):
    """The rendered script, each statement paired with its step result.
    Statements limited to variations other than the run's are left out.
    A table block's rows become one entry, holding each row's steps."""
    closure = store.read_closure(root(), run["report_id"], run["id"])
    text = closure.get(run["script"], "")
    events = store.read_events(root(), run["report_id"], run["id"])

    found = Results(
        started={key(e) for e in events if e["kind"] == "step_start"},
        ended={key(e): e for e in events if e["kind"] == "step_end"},
        calls=call_trees(events),
        attachments={},
        closure=closure,
        finished=finished,
    )
    phases = precondition_phases(events, {i: c for (i, r), c in found.calls.items()
                                          if r is None})
    for index_phases in phases.values():
        for phase in index_phases:
            phase["failure"] = failure_of(closure, phase.get("result"))
    for event in events:
        if event["kind"] == "attachment":
            found.attachments.setdefault(key(event), []).append(event)
    table_rows = {e["index"]: e["rows"] for e in events if e["kind"] == "table_start"}
    row_events = {}
    for event in events:
        if event["kind"] in ("row_start", "row_end"):
            row_events.setdefault((event["index"], event["row"]), {}).update(
                {k: v for k, v in event.items() if k not in ("seq", "ts")})
    variation = (run.get("variation") or {}).get("name")

    statements = get_statements(text)
    in_table = set()
    rows = []
    for index, statement in enumerate(statements):
        if index in in_table:
            continue
        if variation and statement.variations and variation not in statement.variations:
            continue  # limited to other variations: not part of this run
        if statement.table_rows:
            steps = [i for i in range(index + 1, len(statements))
                     if statements[i].table == statement.table]
            steps = steps[:next((n for n, i in enumerate(steps)
                                 if i != index + 1 + n), len(steps))]
            in_table.update(steps)
            rows.append(table_item(statement, index, steps, statements, found,
                                   table_rows.get(index), row_events, variation))
            continue
        item = step_item(statement, index, None, found, phases.get(index, []))
        rows.append(item)

    errors = [e for e in events if e["kind"] == "error"]
    return group(rows, variation), errors


@dataclass
class Results:
    started: set
    ended: dict
    calls: dict
    attachments: dict
    closure: dict
    finished: bool


def step_item(statement, index, row, found, phases=()):
    """One statement with its result (in `row`, for a table block's step)"""
    form = statement.statement
    item = statement_item(
        statement,
        step=isinstance(form, list) and head(form) not in DIRECTIVES,
        calls=found.calls.get((index, row), []),
        phases=phases,
        attachments=found.attachments.get((index, row), []),
    )
    if statement.definition:
        # Definitions aren't steps; only a failed one has a result
        item["step"] = (index, row) in found.ended
    if item["step"]:
        if (index, row) in found.ended:
            ended = found.ended[(index, row)]
            item["state"] = step_state(ended)
            item["result"] = ended
            item["failure"] = failure_of(found.closure, ended)
        elif (index, row) in found.started:
            item["state"] = "running"
        else:
            item["state"] = "not run" if found.finished else "pending"
    return item


def table_item(statement, index, steps, statements, found, names, row_events,
               variation):
    """A table block as one entry: its rows table, then each row with its
    steps' results"""
    item = statement_item(statement, step=True)
    if names is None:  # not reached: the rows as written
        from ..framework.language import parse_table
        names = [row.name for row in parse_table("", statement.statement, [])]
    item["rows"] = []
    for name in names:
        event = row_events.get((index, name), {})
        if "outcome" in event:
            state = {"pass": "pass", "fail": "fail", "error": "error"}[event["outcome"]]
        elif event:
            state = "running"
        else:
            state = "not run" if found.finished else "pending"
        row_steps = [step_item(statements[i], i, name, found) for i in steps
                     if not (variation and statements[i].variations
                             and variation not in statements[i].variations)]
        if state == "pass" and any(s.get("state") == "tbd" for s in row_steps):
            state = "tbd"
        item["rows"].append({"name": name, "values": event.get("values", {}),
                             "state": state, "message": event.get("message"),
                             "steps": row_steps})
    states = [row["state"] for row in item["rows"]]
    item["state"] = min(states, key=STATE_ORDER.index) if states else "not run"
    if "result" not in item:
        item["result"] = None
    return item


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
    return step_state(phase)


def failure_of(files, ended):
    """Why and where a step (or phase) failed, for display, or None. Runs
    from before failures carried a message have none."""
    if not ended or ended.get("passed") or "message" not in ended:
        return None
    return failure_view(files, ended["message"], ended.get("trace"),
                        ended.get("stderr", "") if ended.get("error") else "")


def step_state(ended):
    """pass, fail (an assertion came out false), error (something raised)
    or tbd (it passed, but reached steps not written yet)"""
    if ended["passed"]:
        return "tbd" if ended.get("placeholders") else "pass"
    return "error" if ended.get("error") else "fail"


def call_state(call):
    """A suppressed call (inside try-ok? or try) is true or false; any
    other passes, fails or errs"""
    if "passed" not in call:
        return "running"
    if call.get("suppressed") or call.get("checked"):  # checked: older runs
        return "true" if call["passed"] else "false"
    if call.get("block_kind") == "placeholder":
        return "tbd"
    return step_state(call)


def call_trees(events):
    """(statement index, row) -> its block calls as a tree, quiet calls
    left out. Each call has its `children` (calls made inside a step
    form)."""
    calls = {}
    for event in events:
        if event["kind"] not in ("call_start", "call_end") or event.get("quiet"):
            continue
        call = calls.setdefault((*key(event), event["call"]), {"children": []})
        call.update({k: v for k, v in event.items() if k not in ("kind", "seq", "ts")})
    for call in calls.values():
        call["state"] = call_state(call)

    trees = {}
    for (index, row, _), call in sorted(calls.items(), key=lambda kv: (
            kv[0][0], str(kv[0][1]), kv[0][2])):
        parent = calls.get((index, row, call.get("parent")))
        if parent is not None:
            parent["children"].append(call)
        else:
            trees.setdefault((index, row), []).append(call)
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
    if report_id == models.SCRATCH:
        return redirect(url_for("scratch.index"))
    report = store.load_report(root(), report_id) or abort(404)
    runs = store.list_runs(root(), report_id)
    for run in runs:
        run["status"] = run_status(run)

    rows = rollup.combinations(report, runs, lambda run: run["status"])
    requirements = rollup.requirement_rollup(report, rows)
    touched = rollup.ref_rollup(
        report, rows, lambda run: store.read_events(root(), report_id, run["id"]))
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
        touched=touched,
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
    events = store.read_events(root(), report_id, run_id)
    cleanups = [e for e in events if e["kind"] == "cleanup"]
    return render_template(template, run=run, status=status, finished=finished,
                           rows=rows, errors=errors, files=files,
                           touched=rollup.touched(events), cleanups=cleanups)


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
