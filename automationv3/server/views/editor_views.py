from pathlib import Path
import re
import json
from flask import Blueprint, render_template, request, abort, current_app, make_response

from automationv3.framework import edn
from automationv3.models import Testcase, Document

from ..models import get_workspaces, get_editor, get_document

editor = Blueprint('editor', __name__,
                        template_folder='templates')

@editor.route("<id>/tabs", methods=["GET"])
def tabs(id):
    editor = get_editor(id)

    return make_response(render_template('partials/tabs.html',
                           editor=editor,
                           document=editor.active_document))

@editor.route("<id>/open", methods=["POST"])
def open_document(id):
    if request.args.get('path') is None:
        abort(404)

    path = Path(request.args.get('path')).resolve()
    editor = get_editor(id)

    # For now a path must be within one of our workspaces
    root = next((ws.root for ws in get_workspaces()
                 if path.is_relative_to(ws.root)), None)
    if root is None:
        abort(404)

    document = editor.open(path)
    editor.select_document(document)
    
    resp = tabs(id)
    resp.headers['Hx-Trigger'] = json.dumps({'tab-action': True, 'editor-content-update': True})
    return resp


@editor.route("<id>/tabs/<document_id>", methods=["POST"])
def update_tabs(id, document_id):
    action = request.args.get('action')
    triggers = {'tab-action': action}

    editor = get_editor(id)
    document = get_document(document_id)

    if action in ['select']:
        if editor.active_document != document:
            triggers['editor-content-update'] = True
        editor.select_document(document) 
    elif action == 'close':
        if editor.active_document == document:
            triggers['editor-content-update'] = True
        editor.close(document)
    else:
        abort(404)

    resp = tabs(id)
    resp.headers['Hx-Trigger'] = json.dumps(triggers)
    return resp

visual_editors = {
    'application/rvt+edn': 'partials/editor_rvt.html'
}

@editor.route("<id>/content", methods=["GET"])
def content(id):
    editor = get_editor(id)
    documents = editor.documents()
    active_document = editor.active_document
    testcase = None

    if not active_document:
        return make_response('')

    supports_visual = active_document.mime in visual_editors 
    raw = active_document.meta.get('raw', False)

    if raw:
        template = 'partials/editor.html'
    elif active_document.mime == 'application/rvt+edn':
        template = visual_editors[active_document.mime]
        testcase = Testcase(active_document)
    else:
        template = 'partials/editor.html'

    return render_template(template, 
                           id=id,
                           editor=editor,
                           documents=documents,
                           document=active_document, 
                           raw=raw,
                           supports_visual=supports_visual,
                           testcase=testcase)

testcase_sections = ['title', 'description', 'requirements']

@editor.route("<id>/content-section", methods=["GET"])
def section(id):
    section = request.args.get('section')

    editor = get_editor(id)
    document = editor.active_document
    testcase = Testcase(document)
    edit = request.args.get('edit', False)

    if section not in testcase_sections:
        abort(404)

    template = f'partials/editor/testcase_{section}.html'
    return render_template(template, 
                           id=id,
                           editor=editor,
                           testcase=testcase,
                           document=document,
                           edit=edit)


@editor.route("<id>/content/<document_id>", methods=["POST"])
def update_content(id, document_id):
    action = request.args.get('action')
    
    editor = get_editor(id)
    document = get_document(document_id) 
    triggers = set()
    
    if action == 'save':
        document.save()
        triggers.add('tab-action')
    elif action == 'save-draft':
        content = request.form['value']
        document.save_draft(content)
        triggers.add('tab-action')
    elif action == 'view-raw':
        document.set_meta('raw', True)
        triggers.add('editor-content-update')
    elif action == 'view-visual':
        document.set_meta('raw', False)
        triggers.add('editor-content-update')
    else:
        abort(404)


    resp = make_response('SUCCESS', 200)
    resp.headers['Hx-Trigger'] = json.dumps({k:True for k in triggers}) 
    return resp

@editor.route("<id>/content/<document_id>", methods=["PATCH"])
def update_testcase(id, document_id):
    section = request.args.get('section')
    value = request.form.get('value')

    editor = get_editor(id)
    document = get_document(document_id)
    testcase = Testcase(document)
    
    if section not in testcase_sections:
        abort(404)

    triggers = {'tab-action': 'save-draft'}

    if section == 'title':
       testcase.title = value
    elif section == 'description':
        testcase.description = value

    template = f'partials/editor/testcase_{section}.html'
    resp = make_response(render_template(template, 
                           id=id,
                           testcase=testcase,
                           editor=editor,
                           document=document,
                           edit=False))
    resp.headers['Hx-Trigger'] = json.dumps(triggers)
    return resp



