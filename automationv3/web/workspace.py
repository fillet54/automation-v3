"""Workspace pages: the file tree and the read-only script viewer"""

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
import json
import re

from flask import Blueprint, current_app, render_template, request, abort, make_response

from ..framework.closure import CORE, resolve
from ..framework.rst import write_html_parts
from ..framework.testcase import get_statements
from ..services.workspace import FileNode, find_worktrees
from .db import get_db
from .editor.document import is_binary
from .editor.editor import add_document, select_document


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
    editor_id: int

    @cached_property
    def root_node(self):
        return FileNode(self.root)


def get_workspace(conn, id, root):
    """The workspace `id`, creating it (and its editor) on first use"""
    row = conn.execute(
        "SELECT editor_id FROM workspaces WHERE id = ?", (id,)
    ).fetchone()
    if row is not None:
        return Workspace(id, root, row[0])

    with conn:
        editor_id = conn.execute(
            "INSERT INTO editors(active_tab) VALUES (NULL)"
        ).lastrowid
        conn.execute(
            "INSERT INTO workspaces(id, editor_id) VALUES (?, ?)", (id, editor_id)
        )
    return Workspace(id, root, editor_id)


# Views

bp = Blueprint("workspace", __name__)


def worktrees():
    return find_worktrees(current_app.config["WORKSPACE_PATH"])


def workspace_or_404(id):
    root = worktrees().get(id)
    if root is None:
        abort(404)
    return get_workspace(get_db(), id, root)


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


@bp.route("/<path:id>/open", methods=["POST"])
def open_document(id):
    ws = workspace_or_404(id)
    node = node_or_404(ws, request.args.get("path", ""))
    if not node.is_file():
        abort(404)

    conn = get_db()
    document = add_document(conn, ws.editor_id, node.path)
    select_document(conn, ws.editor_id, document.id)

    resp = make_response("Success")
    resp.headers["Hx-Trigger"] = json.dumps(
        {"tab-action": "open", "editor-content-update": True}
    )
    return resp


# Read-only script viewer


def render_file(path):
    """The file as HTML parts for display"""
    if is_binary(path):
        return None
    text = path.read_text()
    if path.suffix == ".rvt":
        return [statement.html for statement in get_statements(text)]
    if path.suffix == ".rst":
        return write_html_parts([text])
    return None


def render_view(ws, node, errors=None):
    relpath = str(node.relative_path)
    closure = None
    if node.path.suffix == ".rvt" and node.path.name != CORE:
        closure = resolve(ws.root, relpath)
    text = None
    try:
        parts = render_file(node.path)
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
        errors=(errors or []) + (closure.errors if closure else []),
    )


@bp.route("/<path:id>/view", methods=["GET"])
def view(id):
    ws = workspace_or_404(id)
    node = node_or_404(ws, request.args.get("path", ""))
    if not node.is_file():
        abort(404)
    return render_view(ws, node)
