from pathlib import Path
import re
import json
from flask import (
        Blueprint, render_template, request, 
        abort, current_app, make_response, 
        redirect, url_for
)

from ..templates import template_root
from ..workspace import get_workspaces

workspace = Blueprint('workspace', __name__,
                        template_folder=template_root)

@workspace.route("/<path:path>", methods=["GET"])
def index(path):
    workspaces = get_workspaces()
    workspace = get_workspaces(path)
    editor = workspace.editors()

    return render_template('workspace.html', 
                           workspaces=workspaces,
                           workspace=workspace,
                           editor=editor)


# TreeView 
@workspace.app_template_filter()
def is_dir(paths):
    return [p for p in paths if p.is_dir()]

@workspace.app_template_filter()
def is_file(paths):
    return [p for p in paths if p.is_file()]

@workspace.app_template_filter()
def as_id(path):
    return re.sub(r'[^a-zA-Z0-9]', '--', str(path))

@workspace.route("/tree", defaults={'path': ''}, methods=["GET"])
@workspace.route("/tree/<path:path>", methods=["GET", "POST"])
def tree(path):
    workspace_id = request.args.get('workspace_id')
    workspace = get_workspaces(workspace_id)
    fstree = workspace.filesystem_tree() 

    if path == '':
        path = workspace.root

    # ensure path is relative to our root
    if not (workspace.root / path).resolve().is_relative_to(workspace.root):
        abort(404)

    path = (workspace.root / path).resolve().relative_to(workspace.root)
    print(path) 
    if request.method == 'POST':
        fstree.toggle(path)

    return render_template('partials/treeitem.html', 
                           workspace=workspace,
                           node=fstree.node(path),
                           opened=fstree.opened)

@workspace.route("<id>/open", methods=["GET", "POST"])
def open_or_select_document(id):
    if request.args.get('path') is None:
        abort(404)

    path = Path(request.args.get('path')).resolve()
    ws = get_workspaces(id)
    editor = ws.active_editor()

    # path must be within our workspace
    if not path.is_relative_to(ws.root):
        abort(404)

    document = editor.open(path)
    editor.select_document(document)

    resp = make_response("Success")
    resp.headers['Hx-Trigger'] = json.dumps({'tab-action': 'open',
                                             'editor-content-update': True})
    return resp
