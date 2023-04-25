from pathlib import Path
import re
from flask import Blueprint, render_template, request, abort, current_app

from .models import get_db

workspace = Blueprint('workspace', __name__,
                        template_folder='templates')

@workspace.route("/", defaults={'id': 0}, methods=["GET"])
@workspace.route("/<id>", methods=["GET"])
def index(id):
    return render_template('workspace.html', 
                           id=id)

# open file - adds tab and selects tab. returns partial content
# save file - saves file. 
# close file - remove tab. returns partial content

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

@workspace.route("/tree", defaults={'id': 0, 'path': ''}, methods=["GET"])
@workspace.route("<id>/tree", defaults={'path': ''}, methods=["GET"])
@workspace.route("/tree/<path:path>", defaults={'id': 0}, methods=["GET", "POST"])
@workspace.route("<id>/tree/<path:path>", methods=["GET", "POST"])
def tree(id, path):
    root = current_app.config['WORKSPACE_PATH']
    node = Path(path).absolute()

    # ensure path is relative to our root
    if not node.is_relative_to(root):
        abort(404)

    if request.method == 'POST':
        opened = get_db().workspace(id).treeview.toggle_node(node.relative_to(root))
    else:
        opened = get_db().workspace(id).treeview.get_opened()

    # Make absolute path
    opened = {root / rel_path 
              for rel_path in opened}

    return render_template('partials/treeitem.html', 
                           id=id,
                           root=root,
                           node=node,
                           opened=opened)

