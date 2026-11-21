"""Report and run pages, rendered from the filesystem store"""

from dataclasses import asdict
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from werkzeug.security import safe_join

from ..documents.run import duration
from ..framework.uut import uut_types
from ..services import jobs as models
from ..services.reports import runs as report_runs
from ..services import scratch as scratch_service
from ..services.reports import access, build, export, rollup, store
from ..services.reports.data import ReportData
from .auth import base_url as server_url, can_change, mine_only, owner_email, safe_next
from .context import reports_root as root, workspaces
from .db import get_db
from . import documents, report_view
from .docs import serve_in_shell

reports = Blueprint("reports", __name__)

# POSTs that change nothing
READ_ONLY = {"reports.preview", "reports.new", "reports.make_bundle"}


# Pages that only change a report, refused even to look at for non-members
EDIT_PAGES = {"reports.document", "reports.versions"}


def may_change_this():
    """May the current user change the report this request is about? True
    when it's about no report, or scratch (whose runs are each their own)."""
    if "may_change" not in g:
        report_id = (request.view_args or {}).get("report_id")
        if not report_id or report_id == scratch_service.SCRATCH:
            g.may_change = True
        else:
            report = store.load_report(root(), report_id) or abort(404)
            g.may_change = can_change(report)
    return g.may_change


@reports.before_request
def check_change():
    """Only a report's owner, its collaborators and admins change it"""
    changing = request.method == "POST" and request.endpoint not in READ_ONLY
    if (changing or request.endpoint in EDIT_PAGES) and not may_change_this():
        abort(403, "Only the report's owner, its collaborators and admins can change it")
    return None


@reports.context_processor
def change_buttons():
    """`can_change` for every report page: whether to show what changes it"""
    return {"can_change": may_change_this()}


def is_mine(report, email):
    return email is None or access.is_member(report, email)


def run_status(run):
    """The outcome of a finished run, else its job's queue status"""
    if run.get("outcome"):
        return run["outcome"]
    job = models.get_job(get_db(), run["id"])
    return job.status if job else "unknown"


@reports.app_template_filter()
def make_id(text):
    """An anchor as docutils makes it (see documents/core.py :anchor:)"""
    from docutils.nodes import make_id as docutils_id
    return docutils_id(text)


@reports.app_template_filter()
def flatten(fingerprint):
    """A fingerprint's (dotted key, value) pairs, sorted"""
    return sorted(models.flatten(fingerprint).items())


reports.app_template_filter()(duration)


@reports.route("/", methods=["GET"])
def index():
    """Reports, newest first: on a central server, by default only those
    the user owns or collaborates on (?who=everyone for all)"""
    mine = mine_only()
    all_reports = [
        {**report, "summary": report_view.summary(report,
                                                  store.list_runs(root(), report["id"]))}
        for report in store.list_reports(root()) if is_mine(report, mine)
    ]
    return render_template("reports/reports.html", reports=all_reports)


def uut_choices():
    """UUT name -> version ids, newest first, for every UUT plugin"""
    return {name: [v.id for v in reversed(cls().report_versions())]
            for name, cls in sorted(uut_types().items())}


@reports.route("/new", methods=["GET", "POST"])
def new():
    """Create an empty report: a name and a workspace. Its UUT versions
    come from the first tests added to it."""
    branches = sorted(workspaces().branches())
    errors = []
    if request.method == "POST":
        form = request.form
        name = form.get("name", "").strip()
        workspace = form.get("workspace")
        if not name:
            errors.append("A report needs a name")
        if workspace not in branches:
            errors.append("Pick a workspace")
        if not errors:
            report_id = report_runs.create_report(root(), workspace, name,
                                             template=workspace_template(workspace),
                                             owner=owner_email())
            return redirect(url_for("reports.report", report_id=report_id))
    return render_template("reports/new.html", workspaces=branches,
                           form=request.form, errors=errors)


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
            uut = uut_types()[name]() if name in uut_types() else None
            version = uut.find_version(id, uut.report_versions()) if uut else None
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


@reports.route("/<report_id>", methods=["GET"])
def report(report_id):
    """The report's document: live, or once frozen and built, its site"""
    if report_id == scratch_service.SCRATCH:
        return redirect(url_for("scratch.index"))
    report = store.load_report(root(), report_id) or abort(404)
    if store.is_frozen(report) and build.site(root(), report_id) is not None and \
            (build.status(root(), report_id) or {}).get("state") == "done":
        return redirect(url_for("reports.site", report_id=report_id))
    return render_page(report_id, "overview")


@reports.route("/<report_id>/<any(runs, values, history):page>", methods=["GET"])
def report_page(report_id, page):
    if page == "runs":  # the report's document shows its runs
        return redirect(url_for("reports.report", report_id=report_id, **request.args))
    return render_page(report_id, page)


def render_page(report_id, page, errors=(), status=200):
    """One page of a report: its overview, the values its runs touched,
    or its history"""
    report = store.load_report(root(), report_id) or abort(404)
    data = ReportData(root(), report_id, status=run_status,
                      links=documents.LiveLinks(), report=report)

    def lookup(ids):
        return {r.id: (r.text, r.subsystem)
                for r in report_runs.known_requirements(get_db(), ids)}

    view = report_view.build(data, lookup)
    context = dict(
        page=page,
        report=report,
        view=view,
        rows=view["rows"],
        run_status=run_status,
        subsystem=request.args.get("subsystem"),
        skipped=[s for s in report.get("scripts", [])
                 if isinstance(s, dict) and s["skipped"]],
        in_progress=data.in_progress,
        uuts={name: v["id"] for name, v in data.used_uut_versions().items()},
        document=data.document,
        missing=export.missing_fields(report),
        bundles=[p.name for p in export.exports(root(), report_id)],
        errors=list(errors),
        connectors=None,
        text_changed=text_changed(report),
        build=build.status(root(), report_id),
        report_id=report_id,
        log=build_log(report_id),
    )
    if page == "overview":
        live = report_context(report, context["in_progress"], data=data,
                              subsystem=context["subsystem"],
                              text_changed=context["text_changed"])
        context["body"], context["problems"] = documents.report_document(
            export.source(root(), report_id), live, poll=block_poll(report_id, live))
    if page == "values":
        touched = rollup.ref_rollup(report, data.combinations, data.events)
        context["connectors"] = report_view.connectors(touched)
    return render_template(f"reports/{page}.html", **context), status


def report_context(report, in_progress, data=None, **extra):
    """The Context the report's document is shown with, live"""
    return documents.report_context(root(), report["id"], run_status, data=data,
                                    blocks=in_progress, **extra)


def block_poll(report_id, live):
    """How a data block of the report's document refreshes: while runs are
    in progress, from its own URL"""
    if not live.extra.get("blocks"):
        return None
    args = {k: v for k, v in request.args.items() if k == "subsystem"}
    return lambda node: url_for("reports.block", report_id=report_id,
                                serial=node["serial"], **args)


@reports.route("/<report_id>/block/<int:serial>", methods=["GET"])
def block(report_id, serial):
    """One data block of the report's document, as it is now. It keeps
    refreshing itself while runs are in progress."""
    report = store.load_report(root(), report_id) or abort(404)
    in_progress = any(r.get("outcome") is None for r in store.list_runs(root(), report_id))
    live = report_context(report, True, subsystem=request.args.get("subsystem"),
                          text_changed=text_changed(report))
    found = documents.report_block(export.source(root(), report_id), serial, live,
                                   poll=block_poll(report_id, live) if in_progress else None)
    return found if found is not None else abort(404)


@reports.route("/<report_id>/source", methods=["GET", "POST"])
def source(report_id):
    """Edit the report's document: its report.rst, with a live preview"""
    report = store.load_report(root(), report_id) or abort(404)
    errors = []
    text = export.source(root(), report_id)
    if request.method == "POST":
        text = request.form.get("source", "").replace("\r\n", "\n")
        try:
            export.set_source(root(), report_id, text)
        except export.ExportError as e:
            errors.append(str(e))
        else:
            return redirect(url_for("reports.report", report_id=report_id))
    body, problems = documents.report_document(text, report_context(report, False))
    return render_template("reports/source.html", report=report, text=text, body=body,
                           problems=problems, errors=errors,
                           frozen=store.is_frozen(report)), 409 if errors else 200


@reports.route("/<report_id>/preview", methods=["POST"])
def preview(report_id):
    """The document as `source` (being edited) would show it"""
    report = store.load_report(root(), report_id) or abort(404)
    body, problems = documents.report_document(request.form.get("source", ""),
                                               report_context(report, False))
    return render_template("reports/partials/preview.html", body=body, problems=problems)


@reports.route("/<report_id>/template", methods=["POST"])
def refresh_template(report_id):
    """Copy the workspace's report template into the report again (its
    document stays as it is)"""
    report = store.load_report(root(), report_id) or abort(404)
    if store.is_frozen(report):
        return render_page(report_id, "overview", ["The report is frozen: reopen it first"], 409)
    export.install_template(root(), report_id, workspace_template(report.get("workspace")),
                            with_source=False)
    return redirect(url_for("reports.source", report_id=report_id))


def text_changed(report):
    """The tracked requirements whose text in the report's context is no
    longer the text the report recorded when it took them on"""
    recorded = report.get("requirement_snapshots") or {}
    current = report_runs.requirement_versions(get_db(), recorded,
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
    target = safe_next(request.form.get("next"),
                       fallback=url_for("reports.report", report_id=report_id))
    return redirect(target)


def workspace_template(name):
    """The document template of a workspace, else the built-in one"""
    try:
        workspace = workspaces().root(name)
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
    """Freeze the report: its site and PDF build in the background"""
    report = store.load_report(root(), report_id) or abort(404)
    try:
        # BUILD_WAIT builds before answering (tests); else in the background
        export.freeze(root(), report_id, base_url=server_url(),
                      snapshots=report_runs.requirement_snapshots(
                          get_db(), report.get("requirements", {}),
                          report.get("requirement_context")),
                      wait=bool(current_app.config.get("BUILD_WAIT")))
    except export.ExportError as e:
        return render_page(report_id, "overview", [str(e)], 409)
    return redirect(url_for("reports.report", report_id=report_id))


@reports.route("/<report_id>/rebuild", methods=["POST"])
def rebuild(report_id):
    """Build a frozen report's site and PDF again (after a failed build)"""
    report = store.load_report(root(), report_id) or abort(404)
    if not store.is_frozen(report):
        abort(409)
    build.start(root(), report_id, server_url())
    return redirect(url_for("reports.report", report_id=report_id))


@reports.route("/<report_id>/bundle", methods=["POST"])
def make_bundle(report_id):
    """Write the frozen report's bundle (report-<id>.zip), and download it"""
    store.load_report(root(), report_id) or abort(404)
    try:
        path = export.bundle(root(), report_id)
    except export.ExportError as e:
        return render_page(report_id, "overview", [str(e)], 409)
    return send_file(path, as_attachment=True)


@reports.route("/<report_id>/report.pdf", methods=["GET"])
def pdf(report_id):
    """The frozen report's PDF"""
    found = build.pdf_path(root(), report_id)
    return send_file(found) if found.is_file() else abort(404)


@reports.route("/<report_id>/build", methods=["GET"])
def build_status(report_id):
    """A frozen report's build, as it stands: a banner, refreshing itself
    while it builds; once built, the page reloads into the site"""
    store.load_report(root(), report_id) or abort(404)
    found = build.status(root(), report_id) or {}
    response = render_template("reports/partials/build.html", report_id=report_id,
                               build=found, log=build_log(report_id))
    if found.get("state") == "done":
        return response, 200, {"HX-Redirect": url_for("reports.report", report_id=report_id)}
    return response


def build_log(report_id):
    path = build.log_path(root(), report_id)
    return path.read_text(errors="replace")[-4000:] if path.is_file() else ""


@reports.route("/<report_id>/site/", defaults={"filename": "index.html"}, methods=["GET"])
@reports.route("/<report_id>/site/<path:filename>", methods=["GET"])
def site(report_id, filename):
    """The frozen report's site: its pages in the app's shell, with the
    report's actions; everything else as it is"""
    report = store.load_report(root(), report_id) or abort(404)
    folder = build.site(root(), report_id)
    if folder is None:
        return redirect(url_for("reports.report", report_id=report_id))
    return serve_in_shell(folder, filename, "reports/site_shell.html",
                          report=report, bundles=[p.name for p in export.exports(root(), report_id)])


@reports.route("/<report_id>/reopen", methods=["POST"])
def reopen(report_id):  # its build goes too: it no longer describes the report
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
        new_id = report_runs.rerun(get_db(), root(), report_id, run_id, force=force,
                              owner=owner_email())
    except report_runs.Drift as drift:
        return render_template("reports/drift.html", run=run, drift=drift), 409
    except models.QueueError as e:
        return render_page(report_id, "overview", e.errors, 409)
    return redirect(url_for("reports.run", report_id=report_id, run_id=new_id))


@reports.route("/<report_id>/collaborators", methods=["POST"])
def collaborators(report_id):
    """Add a collaborator (email), or remove one (remove=email)"""
    from ..services import accounts
    store.load_report(root(), report_id) or abort(404)
    if request.form.get("remove"):
        access.remove_collaborator(root(), report_id, request.form["remove"])
    else:
        try:
            email = accounts.normal_email(request.form.get("email", ""))
        except accounts.AccountError as e:
            return render_page(report_id, "history", [str(e)], 400)
        access.add_collaborator(root(), report_id, email)
    return redirect(url_for("reports.report_page", report_id=report_id, page="history")
                    + "#people")
