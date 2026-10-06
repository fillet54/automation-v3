"""Workspace pages: the file tree and the read-only script viewer"""

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
import re

from flask import Blueprint, current_app, render_template, request, abort

from ..framework import edn
from ..framework.closure import is_script, resolve
from ..framework.document import has_rvt
from ..framework.rst import write_html_parts
from ..framework.statements import get_statements
from ..services.workspace import FileNode, find_worktrees, is_binary
from .db import get_db
from .grouping import group, statement_item


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


@bp.route("/<path:id>", methods=["GET"])
def index(id):
    return render_template(
        "workspace.html", workspaces=list(worktrees()), workspace=workspace_or_404(id)
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


def render_file(path, variation=None):
    """The file as grouped entries for display (see grouping.group), for
    `variation` (a name) if given"""
    if is_binary(path):
        return None
    text = path.read_text()
    if path.suffix != ".rst":
        return None
    if has_rvt(text):  # a script or core.rst: statements, with results' layout
        return group([statement_item(s) for s in get_statements(text)], variation)
    return [("statement", {"html": html}) for html in write_html_parts([text])]


def written_values(variation):
    """A Variation's value forms, as written"""
    return [edn.writes(form).strip() for form in variation.forms]


def render_view(ws, node, errors=None, variation=None):
    """The script viewer. `variation` (a name the script declares) narrows
    the script to what that variation runs; None shows every variation."""
    relpath = str(node.relative_path)
    closure = None
    if not is_binary(node.path) and is_script(relpath, node.path.read_text()):
        closure = resolve(ws.root, relpath)
    names = [v.name for v in closure.variations] if closure else []
    selected = next((v for v in closure.variations if v.name == variation), None) \
        if closure else None
    text = None
    try:
        parts = render_file(node.path, selected.name if selected else None)
    except Exception as e:  # unreadable script: show it raw
        parts, errors = None, (errors or []) + [f"Could not render: {e}"]
    if parts is None and not is_binary(node.path):
        text = node.path.read_text()
    return render_template(
        "partials/script_view.html",
        workspace=ws,
        path=relpath,
        parts=parts,
        text=text,
        closure=closure,
        variation=selected,
        variation_names=names,
        variation_rows=[(v.name, written_values(v))
                        for v in (closure.variations if closure else [])],
        errors=(errors or []) + (closure.errors if closure else []),
    )


@bp.route("/<path:id>/view", methods=["GET"])
def view(id):
    ws = workspace_or_404(id)
    node = node_or_404(ws, request.args.get("path", ""))
    if not node.is_file():
        abort(404)
    return render_view(ws, node, variation=request.args.get("variation"))
