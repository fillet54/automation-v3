"""Workspace pages: the file tree and the read-only script viewer"""

import difflib
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
import re

from flask import Blueprint, current_app, g, render_template, request, abort

from ..framework import edn
from ..framework.closure import is_script, resolve
from ..framework.document import has_rvt
from ..framework.excerpt import excerpt
from ..framework.rst import write_html_parts
from ..framework.statements import get_statements
from ..services import jobs
from ..services.reports import store
from ..services.requirements import models as requirement_models
from ..services.workspace import FileNode, committed_text, edited_files, find_worktrees, is_binary
from .db import get_db
from .grouping import group, statement_item
from .jobs import checked_in_root, live_environments


def expanded_nodes(conn, workspace_id, root):
    """The set of nodes under `root` that are expanded in the tree view"""
    rows = conn.execute(
        "SELECT path FROM expanded_nodes WHERE workspace_id = ?", (workspace_id,)
    )
    return {FileNode(row[0], root) for row in rows}


def toggle_expanded(conn, workspace_id, node):
    params = (workspace_id, str(node.relative_path))
    with conn:
        deleted = conn.execute(
            "DELETE FROM expanded_nodes WHERE workspace_id = ? AND path = ?", params
        ).rowcount
        if not deleted:
            conn.execute(
                "INSERT INTO expanded_nodes(workspace_id, path) VALUES (?, ?)", params
            )


@dataclass
class Workspace:
    """A git worktree's rvts directory, named by its branch"""

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
    if root is not None:
        g.requirement_context, _ = requirement_models.workspace_context(get_db(), root)


def worktrees():
    return find_worktrees(current_app.config["WORKSPACE_PATH"])


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
    return render_template(
        "workspace.html", workspaces=list(worktrees()), workspace=workspace_or_404(id),
        report=target_report(),
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


def render_file(path, variation=None, diagnostics=()):
    """The file as grouped entries for display (see grouping.group), for
    `variation` (a name) if given. Each statement carries the
    `diagnostics` (views, see diagnostic_views) about lines it covers."""
    if is_binary(path):
        return None
    text = path.read_text()
    if path.suffix != ".rst":
        return None
    if has_rvt(text):  # a script or core.rst: statements, with results' layout
        items = []
        for statement in get_statements(text):
            span = statement.span
            found = [d for d in diagnostics if span is not None and d["line"] is not None
                     and span.line <= d["line"] <= span.end_line]
            for d in found:
                d["inline"] = True
            items.append(statement_item(statement, diagnostics=found))
        return group(items, variation)
    return [("statement", {"html": html}) for html in write_html_parts([text])]


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
        before = committed_text(ws.root, path) or ""
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
    edited = edited_files(ws.root)
    in_work = [f for f in dict.fromkeys([relpath, *(closure.load_order if closure else [])])
               if f in edited]
    source, path = ws.root, node.path
    if files == jobs.CHECKED_IN and in_work:
        source = checked_in_root(ws.id)
        path = source / relpath if source else None
        if path is None or not path.is_file():
            return render_template("partials/script_view.html", workspace=ws, path=relpath,
                                   files=files, in_work=in_work, not_checked_in=True,
                                   closure=None, parts=None, text=None, errors=errors or [],
                                   diagnostics=[], live=[], variation=None)
        closure = resolve(source, relpath) if closure else None
    names = [v.name for v in closure.variations] if closure else []
    selected = next((v for v in closure.variations if v.name == variation), None) \
        if closure else None
    text = None
    diagnostics = diagnostic_views(closure, relpath) if closure else []
    try:
        parts = render_file(path, selected.name if selected else None, diagnostics)
    except Exception as e:  # unreadable script: show it raw
        parts, errors = None, (errors or []) + [f"Could not render: {e}"]
    if parts is None and not is_binary(path):
        text = path.read_text()
    return render_template(
        "partials/script_view.html",
        workspace=ws,
        path=relpath,
        files=files if in_work else jobs.IN_WORK,
        in_work=in_work,
        changes=changes(ws, in_work) if files == "changes" and in_work else None,
        live=sorted(live_environments()),
        parts=parts,
        text=text,
        closure=closure,
        variation=selected,
        variation_names=names,
        variation_rows=[(v.name, written_values(v))
                        for v in (closure.variations if closure else [])],
        reports=jobs.reports_for(current_app.config["REPORTS_PATH"], ws.id)
        if closure and not closure.errors else [],
        target=request.args.get("report", ""),
        errors=(errors or []) + [e for e in (closure.errors if closure else [])
                                 if not closure.diagnostics or e not in diagnostic_errors(closure)],
        diagnostics=diagnostics,
    )


def diagnostic_errors(closure):
    return {str(d) for d in closure.diagnostics if d.severity == "error"}


@bp.route("/<path:id>/view", methods=["GET"])
def view(id):
    ws = workspace_or_404(id)
    node = node_or_404(ws, request.args.get("path", ""))
    if not node.is_file():
        abort(404)
    return render_view(ws, node, variation=request.args.get("variation"),
                       files=request.args.get("files"))
