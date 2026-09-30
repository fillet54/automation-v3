import re
import json
from flask import Blueprint, render_template, request, abort, make_response

from ..templates import template_root
from ..treeviews import FileNode
from ..workspace import get_workspace, get_workspaces

workspace = Blueprint("workspace", __name__, template_folder=template_root)


def node_or_404(workspace, path):
    """The tree node for `path` (relative to the workspace root)"""
    try:
        return FileNode(path, workspace.filesystem_tree().root)
    except ValueError:
        abort(404)


@workspace.route("/<path:id>", methods=["GET"])
def index(id):
    return render_template(
        "workspace.html", workspaces=get_workspaces(), workspace=get_workspace(id)
    )


# TreeView
@workspace.app_template_filter()
def is_dir(paths):
    return [p for p in paths if p.is_dir()]


@workspace.app_template_filter()
def is_file(paths):
    return [p for p in paths if p.is_file()]


@workspace.app_template_filter()
def as_id(path):
    return re.sub(r"[^a-zA-Z0-9]", "--", str(path))


def render_tree(workspace, node):
    return render_template(
        "partials/treeitem.html",
        workspace=workspace,
        node=node,
        opened=workspace.filesystem_tree().opened,
    )


@workspace.route("/<path:id>/tree", methods=["GET"])
def tree(id):
    ws = get_workspace(id)
    return render_tree(ws, ws.filesystem_tree().root)


@workspace.route("/<path:id>/expand", methods=["POST"])
def expand(id):
    ws = get_workspace(id)
    node = node_or_404(ws, request.args.get("path", ""))
    ws.filesystem_tree().toggle(node)
    return render_tree(ws, node)


@workspace.route("/<path:id>/open", methods=["POST"])
def open_document(id):
    ws = get_workspace(id)
    node = node_or_404(ws, request.args.get("path", ""))
    if not node.is_file():
        abort(404)

    editor = ws.active_editor()
    document = editor.open(node.path)
    editor.select_document(document)

    resp = make_response("Success")
    resp.headers["Hx-Trigger"] = json.dumps(
        {"tab-action": "open", "editor-content-update": True}
    )
    return resp
