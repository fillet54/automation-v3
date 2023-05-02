from pathlib import Path
import re
import json
from flask import Blueprint, render_template, request, abort, current_app, make_response

from ..models import get_workspace

editor = Blueprint('editor', __name__,
                        template_folder='templates')

@editor.route("<id>/tabs", methods=["GET"])
def tabs(id):
    editor = get_workspace().editors(id)
    documents = editor.documents()
    active_document = editor.active_document
    
    resp = make_response(
            render_template('partials/tabs.html', 
                            id=id,
                            documents=documents,
                            active_document=active_document))
    return resp

@editor.route("<id>/tabs/<path:path>", methods=["POST"])
def update_tabs(id, path):
    path = Path(path)
    action = request.args.get('action')
    triggers = {'tab-action': action}

    editor = get_workspace().editors(id)
    document = editor.documents(path)

    if action in ['open', 'select']:
        if not document.is_opened:
            document.open()
        if editor.active_document != document:
            triggers['editor-content-update'] = True
        editor.select_document(document) 
    elif action == 'close':
        if editor.active_document == document:
            triggers['editor-content-update'] = True
        document.close()
    else:
        abort(404)

    resp = tabs(id)
    resp.headers['Hx-Trigger'] = json.dumps(triggers)
    return resp

@editor.route("<id>/content", methods=["GET"])
def content(id):
    editor = get_workspace().editors(id)
    documents = editor.documents()
    active_document = editor.active_document
    
    return render_template('partials/editor.html', 
                           id=id,
                           documents=documents,
                           active_document=active_document)

@editor.route("<id>/content/<path:path>", methods=["POST"])
def update_content(id, path):
    path = Path(path)
    action = request.args.get('action')
    
    editor = get_workspace().editors(id)
    document = editor.documents(path)
    
    if action == 'save':
        content = request.form['value']
        document.save(content)
    elif action == 'save-draft':
        content = request.form['value']
        document.save_draft(content)
    else:
        abort(404)


    resp = make_response('SUCCESS', 200)
    resp.headers['Hx-Trigger'] = 'tab-action'
    return resp
