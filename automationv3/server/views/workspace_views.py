from pathlib import Path
import re
from flask import Blueprint, render_template, request, abort, current_app, make_response

from ..models import get_workspace

workspace = Blueprint('workspace', __name__,
                        template_folder='templates')

@workspace.route("/", defaults={'id': 0}, methods=["GET"])
@workspace.route("/<id>", methods=["GET"])
def index(id):
    return render_template('workspace.html', 
                           id=id)

################################
## Tabs
#@workspace.route("/tabs", defaults={'id': 0}, methods=["GET"])
#@workspace.route("<id>/tabs", methods=["GET"])
#def tabs(id):
#    root = current_app.config['WORKSPACE_PATH']
#
#    editor = get_workspace().editor
#    documents = editor.documents()
#    active_document = editor.active_document() 
#    
#    resp = make_response(
#            render_template('partials/tabs.html', 
#                            id=id,
#                            documents=documents,
#                            active_document=active_document))
#    return resp
#
#@workspace.route("/tabs/<path:path>", defaults={'id': 0}, methods=["POST"])
#@workspace.route("<id>/tabs/<path:path>", methods=["POST"])
#def tab_select(id, path):
#    root = current_app.config['WORKSPACE_PATH']
#    path = Path(path)
#
#    editor = get_workspace().editor
#    document = editor.documents(path)
#    editor.select_document(document) 
#
#    resp = tabs(id)
#    resp.headers['Hx-Trigger'] = 'tab-action'
#    return resp
#
#############################
#
## File content
#@workspace.route("/acontent", defaults={'id': 0}, methods=["GET"])
#@workspace.route("<id>/acontent", methods=["GET"])
#def active_content(id):
#    editor = get_workspace().editor
#    documents = editor.documents()
#    active_document = editor.active_document() 
#    
#    return render_template('partials/editor.html', 
#                           id=id,
#                           documents=documents,
#                           active_document=active_document)
#
#@workspace.route("/content/<path:path>", defaults={'id': 0}, methods=["GET", "DELETE", "POST"])
#@workspace.route("<id>/content/<path:path>", methods=["GET", "DELETE", "POST"])
#def content(id, path):
#    'Opens file into a tab or if already open selects that tab'
#    root = current_app.config['WORKSPACE_PATH']
#    node = Path(path).absolute()
#
#    print("HI")
#    
#    if not node.is_relative_to(root) or not node.exists() or node.is_dir():
#        abort(404)
#
#    editor = get_workspace().editor
#    document = editor.documents(node.relative_to(root))
#    documents = editor.documents()
#    active_document = editor.active_document() 
#
#    # handle delete
#    if request.method == 'DELETE':
#        # Pick first tab as active if we are deleting the active document
#        if document == active_document:
#            active_document = documents[0] if len(documents) > 1 else None
#        document.close()
#        documents.remove(document)
#    elif request.method == 'POST':
#        content = request.form['value']
#        is_autosave = request.form.get('autosave', False)
#
#        if not is_autosave:
#            document.save(content)
#        else:
#            document.save_draft(content)
#
#    else: # GET
#        if not document.is_opened:
#            document.open()
#            documents.append(document)
#
#        editor.select_document(document)
#        active_document = document
#     
#    return render_template('partials/editor.html', 
#                           id=id,
#                           documents=documents,
#                           active_document=active_document)

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

@workspace.app_template_filter()
def iterdir_with_opened(dir_path, opened_documents):
    '''Support for 'New' documents'''
    opened_in_this_dir = [path
                   for doc in opened_documents
                   if doc.path_on_disk.parent == dir_path]
    files = [path
             for path in dir_path.iterdir()
             if path.is_file()]
    return sorted(files + opened_in_this_dir)

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

    open_documents = [] # TODO

    if request.method == 'POST':
        opened = get_workspace().treeview.toggle_node(node.relative_to(root))
    else:
        opened = get_workspace().treeview.opened

    # Make absolute path
    opened = {root / rel_path 
              for rel_path in opened}

    return render_template('partials/treeitem.html', 
                           id=id,
                           root=root,
                           node=node,
                           opened=opened,
                           open_documents=open_documents)

