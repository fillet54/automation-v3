from pathlib import Path
import re
from flask import Blueprint, render_template, request, abort, current_app, make_response

from ..models import get_db

workspace = Blueprint('workspace', __name__,
                        template_folder='templates')

@workspace.route("/", defaults={'id': 0}, methods=["GET"])
@workspace.route("/<id>", methods=["GET"])
def index(id):
    tabs = get_db().workspace(id).tabs.get_all()
    nodes = [n for n, active in tabs if active == 1]
    content = ''
    if len(nodes):
        content =  get_db().workspace(id).tabs.get(nodes[0])

    return render_template('workspace.html', 
                           id=id,
                           tabs=tabs,
                           content=content)

# File content
@workspace.route("/content/<path:path>", defaults={'id': 0}, methods=["GET", "DELETE"])
@workspace.route("<id>/content/<path:path>", methods=["GET", "DELETE"])
def content(id, path):
    'Opens file into a tab or if already open selects that tab'
    root = current_app.config['WORKSPACE_PATH']
    node = Path(path).absolute()
    node_rel = node.relative_to(root)
    
    if not node.is_relative_to(root) or not node.exists() or node.is_dir():
        abort(404)
        
    tabs = get_db().workspace(id).tabs.get_all()
    active = node_rel
    current_active = {path for path, active in tabs if active}

    # handle delete
    if request.method == 'DELETE':
        if node_rel in current_active:
            active = tabs[0][0] if len(tabs) > 1 else None
        else:
            # Don't change active if we are not deleting the active tab
            active = None

        get_db().workspace(id).tabs.delete(node_rel)
    else: # GET

        if not any(path for path, active in tabs if path == node_rel):
            try:
                text = node.read_text()
            except:
                text = 'BINARY_FILE'
            get_db().workspace(id).tabs.create(node_rel, text)

    # Render out tabs
    if active:
        get_db().workspace(id).tabs.set_active(active)
        content = get_db().workspace(id).tabs.get(active)
    else:
        content = ''

    tabs = get_db().workspace(id).tabs.get_all()
    
    return render_template('partials/tabs.html', 
                           id=id,
                           tabs=tabs,
                           content=content)

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

