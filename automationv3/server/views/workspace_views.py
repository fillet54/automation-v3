from pathlib import Path
import re
from flask import Blueprint, render_template, request, abort, current_app, make_response, redirect

from ..models import get_workspaces

workspace = Blueprint('workspace', __name__,
                        template_folder='templates')

@workspace.route("/<path:path>", methods=["GET"])
def index(path):
    workspace = get_workspaces(path)
    workspaces = get_workspaces()
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
    path = (workspace.root / path).absolute()
    
    # ensure path is relative to our root
    if not path.is_relative_to(workspace.root):
        abort(404)
        
    path = path.relative_to(workspace.root)

    if request.method == 'POST':
        opened = workspace.treeview.toggle_node(path)
    else:
        opened = workspace.treeview.opened

    
    return render_template('partials/treeitem.html', 
                           workspace=workspace,
                           node=path,
                           opened=opened)

