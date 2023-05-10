from pathlib import Path
import re
import json
from flask import Blueprint, render_template, request, abort, current_app, make_response

from automationv3.framework import edn
from automationv3.models import Testcase

from ..models import get_workspaces

editor = Blueprint('editor', __name__,
                        template_folder='templates')

@editor.route("<id>/tabs", methods=["GET"])
def tabs(id):
    workspace = get_workspaces(request.args.get('workspace_id'))
    editor = workspace.editors(id)
    documents = editor.documents()
    active_document = editor.active_document
    
    resp = make_response(
            render_template('partials/tabs.html', 
                            id=id,
                            workspace=workspace,
                            documents=documents,
                            active_document=active_document))
    return resp

@editor.route("<id>/tabs/<path:path>", methods=["POST"])
def update_tabs(id, path):
    path = Path(path)
    action = request.args.get('action')
    triggers = {'tab-action': action}

    workspace = get_workspaces(request.args.get('workspace_id'))
    editor = workspace.editors(id)
    document = editor.documents(path)

    if action in ['open', 'select']:
        if editor.active_document != document:
            triggers['editor-content-update'] = True
        if not document.is_opened:
            document.open()
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
    workspace = get_workspaces(request.args.get('workspace_id'))
    editor = workspace.editors(id)
    documents = editor.documents()
    active_document = editor.active_document
    testcase = None

    if not active_document:
        return make_response('')

    supports_visual = active_document.mime == 'application/rvt+edn'
    raw = active_document.meta.get('raw', False)

    if not raw and active_document.mime == 'application/rvt+edn':
        template = 'partials/editor_rvt.html'
        testcase = Testcase(active_document)
    else:
        template = 'partials/editor.html'

    return render_template(template, 
                           id=id,
                           workspace=workspace,
                           editor=editor,
                           documents=documents,
                           active_document=active_document, 
                           raw=raw,
                           supports_visual=supports_visual,
                           testcase=testcase)

testcase_sections = ['title', 'description', 'requirements']

@editor.route("<id>/content-section", methods=["GET"])
def section(id):
    section = request.args.get('section')

    workspace = get_workspaces(request.args.get('workspace_id'))
    editor = workspace.editors(id)
    active_document = editor.active_document
    testcase = Testcase(active_document)

    if section not in testcase_sections:
        abort(404)

    template = f'partials/editor/testcase_{section}.html'
    return render_template(template, 
                           id=id,
                           workspace=workspace,
                           editor=editor,
                           testcase=testcase,
                           edit=False)

@editor.route("<id>/content-edit", methods=["GET"])
def edit(id):
    section = request.args.get('section')

    workspace = get_workspaces(request.args.get('workspace_id'))
    editor = workspace.editors(id)
    active_document = editor.active_document
    testcase = Testcase(active_document)

    if section not in testcase_sections:
        abort(404)

    template = f'partials/editor/testcase_{section}.html'
    return render_template(template, 
                           id=id,
                           workspace=workspace,
                           testcase=testcase,
                           editor=editor,
                           active_document=active_document,
                           edit=True)


@editor.route("<id>/content/<path:path>", methods=["POST"])
def update_content(id, path):
    path = Path(path)
    action = request.args.get('action')
    
    workspace = get_workspaces(request.args.get('workspace_id'))
    editor = workspace.editors(id)
    document = editor.documents(path)
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

@editor.route("<id>/content/<path:path>", methods=["PATCH"])
def update_testcase(id, path):
    path = Path(path)
    section = request.args.get('section')
    value = request.form.get('value')


    workspace = get_workspaces(request.args.get('workspace_id'))
    editor = workspace.editors(id)
    active_document = editor.active_document
    document = editor.documents(path)
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
                           workspace=workspace,
                           testcase=testcase,
                           editor=editor,
                           active_document=active_document,
                           edit=False))
    resp.headers['Hx-Trigger'] = json.dumps(triggers)
    return resp



