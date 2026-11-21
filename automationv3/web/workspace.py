"""Workspace pages: the file tree, and the files open in tabs, each shown
as its cards (see editor.py) to read and, in a worktree, to edit"""

import difflib
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
import re

from flask import Blueprint, current_app, g, jsonify, render_template, request, abort

from ..framework import edn, snippets
from ..framework.closure import is_script, resolve
from ..framework.source import has_rvt
from ..framework.excerpt import excerpt
from ..services import jobs
from ..services.reports import store
from ..services.requirements import models as requirement_models
from ..services.workspace import FileNode, is_binary
from .db import get_db
from . import console, documents, editor
from .auth import can_change
from .client_mode import build_choices, central
from .jobs import checked_in_root, live_environments, workspaces


def expanded_nodes(conn, workspace_id, root):
    """The set of nodes under `root` that are expanded in the tree view"""
    from ..services.database import expanded_node_paths
    return {FileNode(path, root) for path in expanded_node_paths(conn, workspace_id)}


def toggle_expanded(conn, workspace_id, node):
    from ..services.database import toggle_expanded_node
    toggle_expanded_node(conn, workspace_id, str(node.relative_path))


@dataclass
class Workspace:
    """A git worktree's scripts folder, named by its branch"""

    id: str
    root: Path

    @cached_property
    def root_node(self):
        return FileNode(self.root)


# Views

bp = Blueprint("workspace", __name__)


@bp.before_request
def requirement_context():
    """:req: references on a workspace's pages read the requirements in
    the context the workspace verifies (see app.requirement_lookup)"""
    root = worktrees().get((request.view_args or {}).get("id"))
    if root is None:
        return
    if current_app.config.get("CENTRAL") is not None:
        # The local client has no requirements of its own: the central
        # server resolves the context the workspace names
        g.requirement_context = configured_context(root)
    else:
        g.requirement_context, _ = requirement_models.workspace_context(get_db(), root)


def configured_context(root):
    """The requirements context named in the workspace's automation.json,
    unchecked; None for trunk"""
    import json
    path = Path(root) / requirement_models.WORKSPACE_CONFIG
    try:
        return json.loads(path.read_text()).get("requirements") or None
    except (OSError, ValueError, AttributeError):
        return None


def worktrees():
    return workspaces().branches()


def workspace_or_404(id):
    root = worktrees().get(id)
    if root is None:
        abort(404)
    return Workspace(id, root)


def node_or_404(workspace, path):
    """The tree node for `path` (relative to the workspace root)"""
    try:
        return FileNode(path, workspace.root_node)
    except ValueError:
        abort(404)


def target_report():
    """The report a test is being added to (`report` argument), or None"""
    report_id = request.args.get("report")
    return store.load_report(current_app.config["REPORTS_PATH"], report_id) \
        if report_id else None


@bp.route("/<path:id>", methods=["GET"])
def index(id):
    ws = workspace_or_404(id)
    tabs, active = editor.open_tabs(get_db(), ws.id)
    tabs = [p for p in tabs if (ws.root / p).is_file()]
    path = request.args.get("path")
    if path:  # a link to a file: it opens in a tab of its own
        tabs, active = (tabs if path in tabs else tabs + [path]), path
    return render_template(
        "workspace.html", workspaces=list(worktrees()), workspace=ws,
        report=target_report(), tabs=tabs, active_tab=active if active in tabs else None,
        editable=editor.editable(), editor_version=editor.script_version(),
        console=editor.editable() and console.console() is not None,
    )


# TreeView
@bp.app_template_filter()
def is_dir(paths):
    return [p for p in paths if p.is_dir()]


@bp.app_template_filter()
def is_file(paths):
    return [p for p in paths if p.is_file()]


@bp.app_template_filter()
def as_id(path):
    return re.sub(r"[^a-zA-Z0-9]", "--", str(path))


def render_tree(workspace, node):
    return render_template(
        "partials/treeitem.html",
        workspace=workspace,
        node=node,
        opened=expanded_nodes(get_db(), workspace.id, workspace.root_node),
    )


@bp.route("/<path:id>/tree", methods=["GET"])
def tree(id):
    ws = workspace_or_404(id)
    return render_tree(ws, ws.root_node)


@bp.route("/<path:id>/expand", methods=["POST"])
def expand(id):
    ws = workspace_or_404(id)
    node = node_or_404(ws, request.args.get("path", ""))
    toggle_expanded(get_db(), ws.id, node)
    return render_tree(ws, node)


# Read-only script viewer


def render_file(path, variation=None, diagnostics=(), variations=True):
    """The file's document as HTML, for `variation` (a name) if given,
    or None if it isn't rst. A script shows the `diagnostics` (views, see
    diagnostic_views) by the statements they are about."""
    if is_binary(path):
        return None
    text = path.read_text()
    if path.suffix != ".rst":
        return None
    if has_rvt(text):  # a script or core.rst: its statements, as a run shows them
        return documents.script_document(text, variation, diagnostics, variations)
    return documents.rst_document(text)


def diagnostic_views(closure, path):
    """The closure's diagnostics for display: errors first, each with an
    excerpt of the code it is about, and `line` set when it is in the
    script at `path` (so it can show by its statement)"""
    views = []
    for d in sorted(closure.diagnostics, key=lambda d: d.severity != "error"):
        span = d.span
        views.append({
            "severity": d.severity,
            "message": str(d)[len(d.where) + 2:] if d.where else str(d),
            "where": d.where,
            "excerpt": excerpt(closure.files, span),
            "line": span.line if span is not None and span.source == path else None,
            "inline": False,
        })
    return views


def written_values(variation):
    """A Variation's value forms, as written"""
    return [edn.writes(form) for form in variation.forms]


VIEWS = (jobs.IN_WORK, jobs.CHECKED_IN, "changes")


def changes(ws, files):
    """[(path, unified diff lines)] from the checked-in text of each of
    `files` to the text on disk"""
    out = []
    for path in files:
        before = workspaces().committed_text(ws.id, path) or ""
        after = (ws.root / path).read_text() if (ws.root / path).is_file() else ""
        out.append((path, list(difflib.unified_diff(
            before.splitlines(), after.splitlines(), "checked in", "in work", lineterm="", n=3))))
    return out


def render_view(ws, node, errors=None, variation=None, files=None):
    """The script viewer. `variation` (a name the script declares) narrows
    the script to what that variation runs; None shows every variation.
    `files` shows the script in work (on disk, the default), as checked
    in, or the changes between them, when it or a file it loads has edits
    that aren't checked in."""
    relpath = str(node.relative_path)
    files = files if files in VIEWS else jobs.IN_WORK
    closure = None
    if not is_binary(node.path) and is_script(relpath, node.path.read_text()):
        closure = resolve(ws.root, relpath)
    edited = workspaces().edited(ws.id)
    in_work = [f for f in dict.fromkeys([relpath, *(closure.load_order if closure else [])])
               if f in edited]
    source, path = ws.root, node.path
    if files == jobs.CHECKED_IN and in_work:
        source = checked_in_root(ws.id)
        path = source / relpath if source else None
        if path is None or not path.is_file():
            return render_template("partials/script_view.html", workspace=ws, path=relpath,
                                   files=files, in_work=in_work, not_checked_in=True,
                                   closure=None, document=None, text=None,
                                   errors=errors or [],
                                   diagnostics=[], live=[], variation=None)
        closure = resolve(source, relpath) if closure else None
    names = [v.name for v in closure.variations] if closure else []
    selected = next((v for v in closure.variations if v.name == variation), None) \
        if closure else None
    text = None
    diagnostics = diagnostic_views(closure, relpath) if closure else []
    cards = file_hash = document = None
    if files == jobs.IN_WORK and selected is None and not is_binary(path):
        # The file as it is on disk, whole: its cards, which a worktree can edit
        documents.ready()
        raw = editor.read(path)
        file_hash = editor.text_hash(raw)
        cards = editor.card_views(path, raw, diagnostics)
    else:
        try:
            document = render_file(path, selected.name if selected else None, diagnostics,
                                   variations=closure is None)
        except Exception as e:  # unreadable script: show it raw
            document, errors = None, (errors or []) + [f"Could not render: {e}"]
        if document is None and not is_binary(path):
            text = path.read_text()
    return render_template(
        "partials/script_view.html",
        workspace=ws,
        path=relpath,
        files=files if in_work else jobs.IN_WORK,
        in_work=in_work,
        changes=changes(ws, in_work) if files == "changes" and in_work else None,
        live=sorted(live_environments()),
        document=document,
        text=text,
        cards=cards,
        file_hash=file_hash,
        editable=editor.editable(),
        closure=closure,
        variation=selected,
        variation_names=names,
        variation_rows=[(v.name, written_values(v))
                        for v in (closure.variations if closure else [])],
        reports=[r for r in jobs.reports_for(current_app.config["REPORTS_PATH"], ws.id)
                 if can_change(r)]
        if closure and not closure.errors else [],
        target=request.args.get("report", ""),
        errors=(errors or []) + [e for e in (closure.errors if closure else [])
                                 if not closure.diagnostics or e not in diagnostic_errors(closure)],
        diagnostics=diagnostics,
        builds=build_choices(closure.uuts)
        if central() is not None and closure and not closure.errors else [],
    )


def diagnostic_errors(closure):
    return {str(d) for d in closure.diagnostics if d.severity == "error"}


@bp.route("/<path:id>/view", methods=["GET"])
def view(id):
    ws = workspace_or_404(id)
    node = node_or_404(ws, request.args.get("path", ""))
    if not node.is_file():
        if node.path.exists() or not editor.editable():
            abort(404)
        # A file the editor made that isn't saved yet: the page fills it in
        return render_template(
            "partials/script_view.html", workspace=ws, path=str(node.relative_path),
            files=jobs.IN_WORK, in_work=[], closure=None, document=None, text=None,
            errors=[], diagnostics=[], live=[], variation=None, cards=[], file_hash="",
            editable=True, unsaved=True)
    return render_view(ws, node, variation=request.args.get("variation"),
                       files=request.args.get("files"))


@bp.route("/<path:id>/snippets", methods=["GET"])
def snippet_list(id):
    """The snippets a file can use (snippets.py): those of every
    snippets.rst from the root down to its folder"""
    ws = workspace_or_404(id)
    path = request.args.get("path") or ""
    if ".." in path.split("/") or path.startswith("/"):
        abort(400)
    # a file's folder: a new file need not be on disk yet
    return jsonify(snippets=[s.as_dict() for s in snippets.collect(ws.root, path or "x")])


editor.register(bp, workspace_or_404, node_or_404)
console.register(bp, workspace_or_404, node_or_404, editor.editable)
