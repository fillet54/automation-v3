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

from ..services import jobs
from ..services.requirements import links, models, render, rst_source, suspects, textdiff
from ..services.workspace import find_worktrees
from .db import get_db

requirements = Blueprint("requirements", __name__)

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
    """branch -> rvts root, or {} when no workspace is configured"""
    path = current_app.config.get("WORKSPACE_PATH")
    return find_worktrees(path) if path else {}


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
        reports=jobs.reports_for(current_app.config.get("REPORTS_PATH"), state.workspace),
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
                                   form.get("context") or "trunk")
        else:
            suspects.review_trace(conn, form["child"], form["parent"])
    except (KeyError, models.ContextError):
        abort(400)
    back = form.get("next") or ""
    return redirect(back if back.startswith("/") and not back.startswith("//")
                    else url_for("requirements.suspect_links"))


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


@requirements.route("/imports", methods=["GET"])
def imports():
    conn = get_db()
    return render_template("requirement_imports.html", log=models.log(conn, 30),
                           **nav(conn, page_state(conn, "trunk"), tab="imports"))


def spec_cache():
    """Where built specs are kept: SPEC_CACHE_PATH, else spec-builds/ beside
    the database"""
    config = current_app.config
    if not config.get("SPEC_CACHE_PATH"):
        db = config.get("DB_PATH")
        config["SPEC_CACHE_PATH"] = (Path(db).resolve().parent / "spec-builds"
                                     if db and db != ":memory:"
                                     else Path(tempfile.mkdtemp(prefix="spec-builds-")))
    return config["SPEC_CACHE_PATH"]


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

    return requirement.__repr_html__()
