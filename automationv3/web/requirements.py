"""Requirements pages: the requirements in a context, one requirement with
its traces and history, what changed between two contexts, suspect
links, the import log, and specs read as documents"""

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from flask import (Blueprint, current_app, render_template, request, abort, redirect,
                   send_from_directory, url_for)
from markupsafe import Markup

from . import editor
from ..services.reports import runs as report_runs
from ..services.requirements import links, models, render, rst_source, suspects, textdiff
from .auth import admin_required, can_change, owner_email, safe_next
from .context import cache_dir
from .db import get_db

requirements = Blueprint("requirements", __name__)


@requirements.before_request
def on_the_central_server():
    """The local client keeps no requirements of its own: its
    requirement pages are the central server's"""
    from .client_mode import central_client
    client = central_client()
    if client is not None:
        query = request.query_string.decode()
        return redirect(client.server + request.path + (f"?{query}" if query else ""))

FACET_LABELS = {"text": "text", "metadata": "attributes", "links": "links",
                "section": "moved", "spec": "spec", "added": "added", "removed": "removed"}
FACET_TONES = {"added": "success", "removed": "danger", "text": "warning"}


@requirements.app_template_filter("facet")
def facet_label(name):
    return FACET_LABELS.get(name, name)


@requirements.app_template_filter("facet_tone")
def facet_tone(name):
    return FACET_TONES.get(name, "neutral")


def workspaces():
    """branch -> scripts folder, or {} when no workspace is configured"""
    source = current_app.config.get("WORKSPACES")
    return source.branches() if source else {}


@dataclass
class State:
    """Where a requirements page is looking: the workspace (?workspace=,
    else the first), the context it verifies (its automation.json), and
    the context shown (?context=, else the workspace's)"""
    workspace: str
    workspaces: list
    context: str
    default: str
    problem: str = None

    @property
    def param(self):
        """?context= for links: None when it's the workspace's own"""
        return None if self.context == self.default else self.context


def page_state(conn, context=None):
    roots = workspaces()
    workspace = request.args.get("workspace") or next(iter(roots), None)
    default, problem = "trunk", None
    if workspace in roots:
        links.refresh(conn, workspace, roots[workspace])
        default, problem = models.workspace_context(conn, roots[workspace])
    else:
        workspace = None
    state = State(workspace, sorted(roots), context or request.args.get("context") or default,
                  default, problem)
    try:
        models.resolve(conn, state.context)
    except models.ContextError:
        abort(404)
    return state


def nav(conn, state, **current):
    """What every requirements page's side column needs"""
    return {"state": state, "context": state.context, "ctx_param": state.param,
            "workspace": state.workspace, "contexts": models.contexts(conn),
            "specs": models.specs(conn, state.context),
            "subsystems": models.subsystems(conn, state.context),
            "selected_spec": current.get("spec"), "selected_subsystem": current.get("subsystem"),
            "tab": current.get("tab", "list")}


def script_suspects(conn, state):
    """(script, requirement id) -> Suspect, for the state's workspace"""
    if not state.workspace:
        return {}
    return {(s.source, s.target): s
            for s in suspects.script_suspects(conn, state.workspace, state.context)}


@requirements.route("/", methods=["GET"])
def list():
    subsystem = request.args.get("subsystem")
    spec = request.args.get("spec")

    conn = get_db()
    state = page_state(conn)
    reqs = models.find_all(conn, subsystem, context=state.context, spec=spec)

    # Scripts referencing each requirement in the chosen workspace
    linked = {}
    if state.workspace:
        linked = links.scripts_by_requirement(conn, state.workspace)
        if not subsystem and not spec:
            known = {r.id for r in reqs}
            reqs += [models.Requirement(id) for id in sorted(linked) if id not in known]

    return render_template(
        "requirements.html",
        requirements=reqs,
        linked=linked,
        suspect=script_suspects(conn, state),
        workspaces=state.workspaces,
        hx_request=request.headers.get("HX-Request", False),
        reports=[r for r in report_runs.reports_for(current_app.config.get("REPORTS_PATH"),
                                             state.workspace) if can_change(r)],
        target=request.args.get("report", ""),
        **nav(conn, state, spec=spec, subsystem=subsystem),
    )


def text_diff(before, after):
    """Word differences between two Requirements' texts, as plain text"""
    return textdiff.word_diff(rst_source.plain_text(before.text),
                              rst_source.plain_text(after.text))


def what_changed(before, after, unhashed=None):
    """The details of a change between two Requirements, for the page.
    Attributes in `unhashed` (spec -> names) change without it counting,
    so they're left out."""
    if before is None or after is None:
        return None
    skip = (unhashed or {}).get(after.spec, set())
    return {"text": text_diff(before, after) if before.text != after.text else None,
            "attributes": [d for d in textdiff.dict_diff(before.attributes, after.attributes)
                           if d[0] not in skip],
            "satisfies": (sorted(set(before.satisfies) - set(after.satisfies)),
                          sorted(set(after.satisfies) - set(before.satisfies))),
            "section": (before.section, after.section) if before.section != after.section
            else None}


@requirements.route("/req/<id>", methods=["GET"])
def requirement(id):
    conn = get_db()
    state = page_state(conn)
    found = models.find_by_id(conn, id, state.context)
    events = models.history(conn, id)
    if found is None and not events:
        abort(404)
    unhashed = models.unhashed_attributes(conn)
    in_trunk = state.context == "trunk"
    traces = {(s.source, s.target): s for s in suspects.trace_suspects(conn)} if in_trunk else {}
    parents = []
    for target in (found.satisfies if found else ()):
        parent = models.find_by_id(conn, target, state.context)
        change = None
        if (id, target) in traces:
            change = what_changed(suspects.reviewed_version(conn, target, traces[(id, target)].reviewed),
                                  parent, unhashed)
        parents.append((target, parent, (id, target) in traces, change))
    children = [(c, (c.id, id) in traces) for c in models.satisfied_by(conn, id, state.context)]
    scripts = []
    if state.workspace:
        suspect = script_suspects(conn, state)
        for script in links.scripts_by_requirement(conn, state.workspace).get(id, []):
            s = suspect.get((script, id))
            change = what_changed(suspects.reviewed_version(conn, id, s.reviewed), found,
                                  unhashed) if s else None
            scripts.append((script, s, change))
    return render_template(
        "requirement.html", requirement=found, id=id, parents=parents, children=children,
        can_edit=editor.editable(),
        events=[(e, what_changed(e.before, e.requirement, unhashed)) for e in reversed(events)],
        scripts=scripts, in_trunk=in_trunk,
        **nav(conn, state, spec=found.spec if found else None, tab="list"))


@requirements.route("/suspects", methods=["GET"])
def suspect_links():
    conn = get_db()
    state = page_state(conn)
    unhashed = models.unhashed_attributes(conn)

    def detail(s):
        current = models.find_by_id(conn, s.target, "trunk" if s in traces else state.context)
        return s, what_changed(suspects.reviewed_version(conn, s.target, s.reviewed), current,
                               unhashed)

    traces = suspects.trace_suspects(conn)
    return render_template(
        "requirement_suspects.html",
        scripts=[detail(s) for s in script_suspects(conn, state).values()],
        traces=[detail(s) for s in traces],
        **nav(conn, state, tab="suspects"))


@requirements.route("/review", methods=["POST"])
def review():
    """Mark a suspect link reviewed: a script's (workspace, script, id,
    context) or a trace's (child, parent)"""
    conn = get_db()
    form = request.form
    try:
        if form.get("script"):
            suspects.review_script(conn, form["workspace"], form["script"], form["id"],
                                   form.get("context") or "trunk", by=owner_email())
        else:
            suspects.review_trace(conn, form["child"], form["parent"], by=owner_email())
    except (KeyError, models.ContextError):
        abort(400)
    return redirect(safe_next(form.get("next"),
                              fallback=url_for("requirements.suspect_links")))


@requirements.route("/changes", methods=["GET"])
def changes():
    conn = get_db()
    choices = models.contexts(conn)
    sets = [c for c, _ in choices if c.startswith("set:")]
    before = request.args.get("from") or (sets[0] if sets else "trunk")
    after = request.args.get("to") or "trunk"
    spec, subsystem = request.args.get("spec") or None, request.args.get("subsystem") or None
    try:
        found = models.diff(conn, before, after, spec=spec, subsystem=subsystem)
    except models.ContextError:
        abort(404)
    unhashed = models.unhashed_attributes(conn)
    return render_template(
        "requirement_changes.html", before=before, after=after, choices=choices,
        changes=[(c, what_changed(c.before, c.after, unhashed)) for c in found],
        **nav(conn, page_state(conn, after), spec=spec, subsystem=subsystem, tab="changes"))


def render_imports(outcome=None, errors=(), status=200):
    conn = get_db()
    return render_template("requirement_imports.html", log=models.log(conn, 30),
                           importers=models.importers(conn), outcome=outcome,
                           errors=[*errors],
                           **nav(conn, page_state(conn, "trunk"), tab="imports")), status


@requirements.route("/imports", methods=["GET"])
def imports():
    return render_imports()


def import_upload(data, name, **flat_options):
    """Import an uploaded file (a zipped export, or a CSV or list as a
    spec: see export.read_upload) as the current user. Returns (import
    id, outcomes). Raises export.ExportError."""
    from ..services.requirements import export, store
    found = export.read_upload(data, name, **flat_options)
    return store.import_export(get_db(), found, source=name, by=owner_email())


@requirements.route("/imports", methods=["POST"])
@admin_required
def upload_import():
    """Import a DOORS export folder, zipped (admins only). A spreadsheet
    or a list goes on to the page that matches its columns and previews
    it, unless the form already names its spec."""
    from ..services.requirements import export, flat, staging
    upload = request.files.get("export")
    if upload is None or not upload.filename:
        return render_imports(errors=["Choose a file to import"], status=400)
    form = request.form
    data = upload.read()
    if flat.is_flat(upload.filename) and not form.get("spec", "").strip():
        token = staging.stage(staging_root(), data, upload.filename)
        return redirect(url_for("requirements.sheet_import", token=token))
    try:
        import_id, outcomes = import_upload(
            data, upload.filename, spec=form.get("spec", "").strip(),
            baseline=form.get("baseline", "").strip() or None,
            title=form.get("title", "").strip() or None,
            level=form.get("level") or None, parents=form.get("parents", "").split(","))
    except export.ExportError as e:
        return render_imports(errors=str(e).splitlines(), status=400)
    return render_imports(outcome={"id": import_id, "lines": outcomes})


def staging_root():
    """Where uploads wait to be imported: STAGING_PATH, else uploads/
    beside the database"""
    return cache_dir(current_app.config, "STAGING_PATH", "uploads")


ROLE_CHOICES = [("", "Ignore"), ("id", "Id"), ("text", "Text"), ("satisfies", "Satisfies"),
                ("section", "Section"), ("attribute", "Attribute")]


@dataclass
class SheetForm:
    """The sheet import page's choices: the spec, and for a spreadsheet
    its sheet and each column's role"""
    spec: str = ""
    title: str = ""
    baseline: str = ""
    level: str = "software"
    parents: str = ""
    sheet: str = None
    columns: object = None  # flat.Columns
    problems: list = None

    def params(self, headers):
        """The choices as form fields, to carry to the import"""
        out = {"spec": self.spec, "title": self.title, "baseline": self.baseline,
               "level": self.level, "parents": self.parents}
        if self.sheet:
            out["sheet"] = self.sheet
        if self.columns is not None:
            for i in range(len(headers)):
                role = next((r for r in ("id", "text", "satisfies", "section")
                             if getattr(self.columns, r) == i), None)
                if role is None and i in self.columns.attributes:
                    role = "attribute"
                    out[f"attr_{i}"] = self.columns.attributes[i]
                out[f"role_{i}"] = role or ""
        return out


def sheet_form(values, headers, remembered):
    """The SheetForm in `values` (the page's query or its import form);
    on the first visit, the choices the same file had last time, or
    guesses"""
    from ..services.requirements import flat
    if "spec" not in values:
        last = remembered or {}
        columns = None
        if headers is not None:
            columns = (flat.Columns.from_headers(last["columns"], headers)
                       if last.get("columns") else flat.guess(headers))
        return SheetForm(spec=last.get("spec") or "", title=last.get("title") or "",
                         level=last.get("level") or "software",
                         parents=", ".join(last.get("parents") or []),
                         sheet=last.get("sheet"), columns=columns)
    form = SheetForm(spec=values.get("spec", "").strip(), title=values.get("title", "").strip(),
                     baseline=values.get("baseline", "").strip(),
                     level=values.get("level") or "software",
                     parents=values.get("parents", "").strip(),
                     sheet=values.get("sheet") or None, problems=[])
    if headers is not None:
        form.columns = flat.Columns()
        for i, header in enumerate(headers):
            role = values.get(f"role_{i}", "")
            label = header or f"column {i + 1}"
            if role in ("id", "text", "satisfies", "section"):
                if getattr(form.columns, role) is not None:
                    form.problems.append(f"Two columns are the {role}: pick one")
                else:
                    setattr(form.columns, role, i)
            elif role == "attribute":
                name = values.get(f"attr_{i}", "").strip() or flat.attribute_name(header)
                if not name:
                    form.problems.append(f"Name the attribute {label} becomes")
                form.columns.attributes[i] = name
    return form


def staged_or_404(token):
    from ..services.requirements import staging
    found = staging.load(staging_root(), token)
    if found is None:
        abort(404, "That upload is gone: uploads are kept for a day. Upload it again.")
    return found


def read_staged(data, name, form):
    """(Export or None, problems) for a staged file read as `form` says"""
    from ..services.requirements import export, flat
    if form.problems:
        return None, form.problems
    try:
        return flat.read(data, name, form.spec, baseline=form.baseline or None,
                         title=form.title or None, level=form.level,
                         parents=form.parents.split(","), columns=form.columns,
                         sheet=form.sheet), []
    except export.ExportError as e:
        return None, str(e).splitlines()


@requirements.route("/imports/sheet/<token>", methods=["GET"])
@admin_required
def sheet_import(token):
    """Match a staged spreadsheet's columns, and preview its import"""
    from ..services.requirements import export, flat, staging
    data, name = staged_or_404(token)
    conn = get_db()
    remembered = staging.remembered(conn, name) if "spec" not in request.args else None
    table, table_error = None, None
    if flat.is_sheet(name):
        sheet = request.args.get("sheet") or (remembered or {}).get("sheet")
        try:
            table = flat.table(data, name, sheet)
        except export.ExportError as e:
            if sheet and "spec" not in request.args:
                table = flat.table(data, name)  # last time's sheet is gone
            else:
                table_error = str(e)
    headers = table.headers if table is not None else None
    form = sheet_form(request.args, headers, remembered)
    if table is not None:
        form.sheet = table.sheet
    preview, problems = None, []
    if "spec" in request.args and table_error is None:
        found, problems = read_staged(data, name, form)
        if found is not None:
            preview = staging.preview(conn, found)
    samples = []
    if table is not None:
        for i in range(len(table.headers)):
            values = [row[i] for _, row in table.rows if row[i]]
            samples.append(values[:3])
    known = {s.key: s for s in models.specs(conn)}
    return render_template(
        "requirement_sheet_import.html", token=token, name=name, table=table,
        table_error=table_error, samples=samples, form=form, roles=ROLE_CHOICES,
        params=form.params(headers or []), preview=preview, problems=problems,
        remembered=remembered, known_specs=known, levels=export.LEVELS,
        row_count=len(table.rows) if table is not None else None,
        unhashed=models.unhashed_attributes(conn), what_changed=what_changed,
        **nav(conn, page_state(conn, "trunk"), tab="imports"))


@requirements.route("/imports/sheet/<token>", methods=["POST"])
@admin_required
def sheet_import_commit(token):
    """Import a staged spreadsheet or list as the form says"""
    from ..services.requirements import export, flat, staging, store
    data, name = staged_or_404(token)
    headers = None
    if flat.is_sheet(name):
        try:
            headers = flat.table(data, name, request.form.get("sheet") or None).headers
        except export.ExportError as e:
            return render_imports(errors=[str(e)], status=400)
    form = sheet_form(request.form, headers, None)
    found, problems = read_staged(data, name, form)
    if found is None:
        return render_imports(errors=problems, status=400)
    try:
        import_id, outcomes = store.import_export(get_db(), found, source=name,
                                                  by=owner_email())
    except export.ExportError as e:  # e.g. a baseline imported before
        return render_imports(errors=str(e).splitlines(), status=400)
    staging.drop(staging_root(), token)
    return render_imports(outcome={"id": import_id, "lines": outcomes})


def spec_cache():
    """Where built specs are kept: SPEC_CACHE_PATH, else spec-builds/ beside
    the database"""
    return cache_dir(current_app.config, "SPEC_CACHE_PATH", "spec-builds")


REQ_LINK = re.compile(r'href="@req/([^"#]+)"')


@requirements.app_template_global("spec_link")
def spec_link(context, key, id=None, doc=None):
    """The spec page showing requirement `id` (or document `doc`)"""
    if doc in (None, "index"):
        url = url_for("requirements.spec", context=context, key=key)
    else:
        url = url_for("requirements.spec", context=context, key=key, doc=doc)
    return url + (f"#{id}" if id else "")


@requirements.route("/spec/<context>/<key>/", defaults={"doc": "index"})
@requirements.route("/spec/<context>/<key>/<path:doc>/")
def spec(context, key, doc):
    conn = get_db()
    try:
        versions = models.resolve(conn, context)
    except models.ContextError:
        abort(404)
    if key not in versions:
        abort(404)
    info = next(s for s in models.specs(conn, context) if s.key == key)
    state = page_state(conn, context)
    page = toc = problem = None
    try:
        out = render.build(conn, versions[key], spec_cache())
        page = render.page(out, doc)
        if page is None:
            abort(404)
        toc = render.nav(out)
        wanted = request.args.get("req")
        if wanted and wanted in toc.get("requirements", {}):
            return redirect(spec_link(context, key, id=wanted, doc=toc["requirements"][wanted]))
        page["body"] = Markup(REQ_LINK.sub(
            lambda m: f'href="{url_for("requirements.requirement", id=m.group(1), context=state.param)}"',
            page["body"]))
    except render.RenderError as e:
        problem = str(e)
    return render_template(
        "spec.html", spec=info, doc=doc, page=page, toc=toc, problem=problem,
        requirements=models.find_all(conn, context=context, spec=key) if problem else [],
        spec_contexts=[(c, label) for c, label in models.contexts(conn)
                       if c == "trunk" or c.startswith("set:") or c.startswith(key + "@")],
        **nav(conn, state, spec=key, tab="spec"))


@requirements.route("/spec", methods=["GET"])
def spec_in():
    """A spec in the context chosen on a form (?key=&context=)"""
    return redirect(spec_link(request.args.get("context") or "trunk", request.args["key"]))


@requirements.route("/spec/<context>/<key>/_images/<path:filename>")
def spec_image(context, key, filename):
    conn = get_db()
    try:
        version = models.resolve(conn, context)[key]
        out = render.build(conn, version, spec_cache())
    except (models.ContextError, KeyError, render.RenderError):
        abort(404)
    return send_from_directory(Path(out) / "_images", filename)


@requirements.route("/<id>", methods=["GET"])
def by_id(id):
    requirement = models.find_by_id(get_db(), id)

    if requirement is None:
        abort(404)

    from ..documents.html import requirement_html
    return requirement_html(requirement)
