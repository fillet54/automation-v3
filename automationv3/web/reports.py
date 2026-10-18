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

from ..framework.uut import uut_types
from ..services import jobs as models
from ..services.reports import export, rollup, store
from ..services.workspace import find_worktrees
from .db import get_db
from . import documents, report_view

reports = Blueprint("reports", __name__)


def root():
    return current_app.config["REPORTS_PATH"]


def run_status(run):
    """The outcome of a finished run, else its job's queue status"""
    if run.get("outcome"):
        return run["outcome"]
    job = models.get_job(get_db(), run["id"])
    return job.status if job else "unknown"


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


@reports.route("/", methods=["GET"])
def index():
    all_reports = [
        {**report, "summary": report_view.summary(report,
                                                  store.list_runs(root(), report["id"]))}
        for report in store.list_reports(root())
    ]
    return render_template("reports/reports.html", reports=all_reports)


def uut_choices():
    """UUT name -> version ids, newest first, for every UUT plugin"""
    return {name: [v.id for v in reversed(cls().list_versions())]
            for name, cls in sorted(uut_types().items())}


@reports.route("/new", methods=["GET", "POST"])
def new():
    """Create an empty report: a name and a workspace. Its UUT versions
    come from the first tests added to it."""
    workspaces = sorted(find_worktrees(current_app.config["WORKSPACE_PATH"]))
    errors = []
    if request.method == "POST":
        form = request.form
        name = form.get("name", "").strip()
        workspace = form.get("workspace")
        if not name:
            errors.append("A report needs a name")
        if workspace not in workspaces:
            errors.append("Pick a workspace")
        if not errors:
            report_id = models.create_report(root(), workspace, name,
                                             template=workspace_template(workspace))
            return redirect(url_for("reports.report", report_id=report_id))
    return render_template("reports/new.html", workspaces=workspaces,
                           form=request.form, errors=errors)


def report_uuts(report, runs):
    """uut -> the report's version id, for the UUTs its runs use"""
    current = report.get("uut_versions") or {}
    return {name: current[name]["id"] for name in rollup.used_uuts(runs) if name in current}


@reports.route("/<report_id>/versions", methods=["GET", "POST"])
def versions(report_id):
    """Change the report's UUT versions. Nothing is queued: combinations
    whose latest run used other versions become outdated, until Update
    tests or Rerun brings them up to date."""
    report = store.load_report(root(), report_id) or abort(404)
    runs = store.list_runs(root(), report_id)
    used = rollup.used_uuts(runs)
    current = report.get("uut_versions") or {}
    choices = uut_choices()
    chosen = {name: request.values.get(f"version-{name}") or current.get(name, {}).get("id")
              for name in used}
    chosen = {name: id for name, id in chosen.items() if id}
    in_progress = any(run.get("outcome") is None for run in runs)
    errors = []
    if store.is_frozen(report):
        errors.append("The report is frozen: reopen it to change its versions")
    elif in_progress:
        errors.append("Runs are in progress: change versions once they finish")

    if request.method == "POST" and not errors:
        updated = dict(current)
        for name, id in chosen.items():
            version = uut_types()[name]().find_version(id) if name in uut_types() else None
            if version is None:
                errors.append(f"{name} has no version {id}")
            else:
                updated[name] = asdict(version)
        if not errors:
            store.update_report(root(), report_id, uut_versions=updated)
            return redirect(url_for("reports.report", report_id=report_id))

    template = "reports/versions.html"
    if request.headers.get("HX-Request"):
        template = "reports/partials/versions_form.html"
    return render_template(
        template, report=report, used=used, choices=choices, chosen=chosen,
        current={name: v["id"] for name, v in current.items()},
        outdated_now=rollup.outdated_by(report, runs, {n: current[n]["id"]
                                                        for n in used if n in current}),
        outdated_after=rollup.outdated_by(report, runs, chosen),
        errors=errors,
    ), (409 if errors and request.method == "POST" else 200)


PAGES = ("overview", "runs", "values", "history")


@reports.route("/<report_id>", methods=["GET"])
def report(report_id):
    if report_id == models.SCRATCH:
        return redirect(url_for("scratch.index"))
    return render_page(report_id, "overview")


@reports.route("/<report_id>/<any(runs, values, history):page>", methods=["GET"])
def report_page(report_id, page):
    return render_page(report_id, page)


def render_page(report_id, page, errors=(), status=200):
    """One page of a report: its overview, its runs by subsystem and
    requirement, the values its runs touched, or its history"""
    report = store.load_report(root(), report_id) or abort(404)
    runs = store.list_runs(root(), report_id)
    for run in runs:
        run["status"] = run_status(run)

    def lookup(ids):
        return {r.id: (r.text, r.subsystem)
                for r in models.known_requirements(get_db(), ids)}

    view = report_view.build(root(), report, runs, lambda run: run["status"], lookup)
    context = dict(
        page=page,
        report=report,
        view=view,
        rows=view["rows"],
        subsystem=request.args.get("subsystem"),
        skipped=[s for s in report.get("scripts", [])
                 if isinstance(s, dict) and s["skipped"]],
        in_progress=any(run.get("outcome") is None for run in runs),
        uuts=report_uuts(report, runs),
        document=export.document_fields(report),
        missing=export.missing_fields(report),
        bundles=[p.name for p in export.exports(root(), report_id)],
        errors=list(errors),
        connectors=None,
        text_changed=text_changed(report),
    )
    if page == "values":
        touched = rollup.ref_rollup(
            report, view["rows"],
            lambda run: store.read_events(root(), report_id, run["id"]))
        context["connectors"] = report_view.connectors(touched)
    return render_template(f"reports/{page}.html", **context), status


def text_changed(report):
    """The tracked requirements whose text in the report's context is no
    longer the text the report recorded when it took them on"""
    recorded = report.get("requirement_snapshots") or {}
    current = models.requirement_versions(get_db(), recorded,
                                          report.get("requirement_context"))
    return {id for id, v in recorded.items()
            if id in current and current[id]["text_hash"] != v.get("text_hash")}


@reports.route("/<report_id>/rename", methods=["POST"])
def rename(report_id):
    """Rename the report: its name is its document's title too"""
    store.load_report(root(), report_id) or abort(404)
    try:
        export.rename(root(), report_id, request.form.get("name", ""))
    except export.ExportError as e:
        return render_page(report_id, "overview", [str(e)], 409)
    target = request.form.get("next", "")
    if not target.startswith("/") or target.startswith("//"):  # only back to this site
        target = url_for("reports.report", report_id=report_id)
    return redirect(target)


def server_url():
    """The server's base URL, for links from exported documents: the
    SERVER_URL setting, else the URL this request came in on"""
    return current_app.config.get("SERVER_URL") or request.host_url


def workspace_template(name):
    """The document template of a workspace, else the built-in one"""
    try:
        workspace = find_worktrees(current_app.config["WORKSPACE_PATH"]).get(name)
    except Exception:  # not a git repository, or git missing
        workspace = None
    return export.find_template(workspace)


def report_template(report):
    """The template the report renders with"""
    return export.report_template(root(), report["id"])


@reports.route("/<report_id>/document", methods=["GET", "POST"])
def document(report_id):
    """Edit the report's document fields: number, revision and author,
    who signs it, and its applicable and reference documents (its title
    is the report's name)"""
    report = store.load_report(root(), report_id) or abort(404)
    if store.is_frozen(report):
        return redirect(url_for("reports.report", report_id=report_id))
    fields = export.document_fields(report)
    roles = export.template_settings(report_template(report))["roles"]
    roles += [r for r in fields["signatures"] if r not in roles]
    if request.method == "POST":
        form = request.form
        export.set_document(
            root(), report_id,
            **{name: form.get(name, "").strip()
               for name in ("number", "revision", "author")},
            signatures={role: form.get(f"sign-{n}", "").strip()
                        for n, role in enumerate(roles) if form.get(f"sign-{n}", "").strip()},
            documents=[*export.parse_documents(form.get("applicable", ""), "applicable"),
                       *export.parse_documents(form.get("reference", ""), "reference")],
        )
        return redirect(url_for("reports.report", report_id=report_id))
    return render_template(
        "reports/document.html", report=report, fields=fields, roles=roles,
        applicable=export.format_documents(fields["documents"], "applicable"),
        reference=export.format_documents(fields["documents"], "reference"))


@reports.route("/<report_id>/export", methods=["POST"])
def export_report(report_id):
    """Freeze the report and write its PDF and bundle"""
    report = store.load_report(root(), report_id) or abort(404)
    try:
        export.export(root(), report_id, base_url=server_url(),
                      snapshots=models.requirement_snapshots(
                          get_db(), report.get("requirements", {}),
                          report.get("requirement_context")))
    except export.ExportError as e:
        return render_page(report_id, "overview", [str(e)], 409)
    return redirect(url_for("reports.report", report_id=report_id))


@reports.route("/<report_id>/reopen", methods=["POST"])
def reopen(report_id):
    store.load_report(root(), report_id) or abort(404)
    export.reopen(root(), report_id)
    return redirect(url_for("reports.report", report_id=report_id))


@reports.route("/<report_id>/exports/<name>", methods=["GET"])
def bundle(report_id, name):
    """An exported bundle: report-<id>.zip"""
    found = [p for p in export.exports(root(), report_id) if p.name == name]
    return send_file(found[0], as_attachment=True) if found else abort(404)


@reports.route("/<report_id>/runs/<run_id>", methods=["GET"])
def run(report_id, run_id):
    run = store.load_run(root(), report_id, run_id) or abort(404)
    status = run_status(run)
    finished = run.get("outcome") is not None
    events = store.read_events(root(), report_id, run_id)
    seen = request.args.get("seen", type=int)
    if request.headers.get("HX-Request") and seen == len(events) and not finished:
        return "", 204  # nothing new: the page stays as it is

    template = "reports/run.html"
    if request.headers.get("HX-Request"):
        template = "reports/partials/run_body.html"
    files = store.list_files(root(), report_id, run_id)
    errors = [e for e in events if e["kind"] == "error"]
    document = documents.run_document(
        root(), report_id, run, lambda r: run_status(r),
        [export.report_template(root(), report_id) / "snippets"])
    cleanups = [e for e in events if e["kind"] == "cleanup"]
    report = store.load_report(root(), report_id)
    frozen = store.is_frozen(report)
    stale = rollup.stale_versions(report, run) if report else {}
    current = (report or {}).get("uut_versions") or {}
    return render_template(template, run=run, status=status, finished=finished,
                           document=document, seen=len(events), errors=errors,
                           files=files, frozen=frozen,
                           rerun_on=", ".join(f"{n} {current[n]['id']}" for n in sorted(stale)),
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
    except models.QueueError as e:
        return render_page(report_id, "overview", e.errors, 409)
    return redirect(url_for("reports.run", report_id=report_id, run_id=new_id))
