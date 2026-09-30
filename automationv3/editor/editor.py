from dataclasses import dataclass, field
import json

from flask import Blueprint, render_template, request, abort, make_response

from .document import (
    Document,
    document_from_row,
    open_document,
    get_document,
    delete_document,
    save_document,
    save_draft,
    set_meta,
)
from ..database import get_db
from ..framework import edn
from ..framework.testcase import EdnTestCase
from ..jobqueue import sqlqueue


@dataclass
class Editor:
    """A set of open documents (tabs), one of which may be active"""

    id: int
    documents: list[Document] = field(default_factory=list)
    active_document: Document = None


def create_editor(conn):
    with conn:
        id = conn.execute("INSERT INTO editors(active_tab) VALUES (NULL)").lastrowid
    return Editor(id)


def get_editor(conn, id):
    row = conn.execute("SELECT active_tab FROM editors WHERE id = ?", (id,)).fetchone()
    if row is None:
        return None
    active_tab = row[0]

    rows = conn.execute(
        """
        SELECT d.id, d.path, d.mime, d.st_mtime, d.draft, d.meta
        FROM opened_documents o JOIN documents d ON d.id = o.document_id
        WHERE o.editor_id = ?
        ORDER BY o.id
        """,
        (id,),
    )
    documents = [document_from_row(row) for row in rows]

    # Fall back to the first tab if the active document is gone
    active = None
    if active_tab is not None:
        active = next((d for d in documents if d.id == active_tab), None)
        if active is None or not active.path.exists():
            active = documents[0] if documents else None

    return Editor(id, documents, active)


def add_document(conn, editor_id, path):
    """Opens the file at `path` as a tab in the editor"""
    document = open_document(conn, path)
    with conn:
        conn.execute(
            """
            INSERT INTO opened_documents(editor_id, document_id)
            SELECT ?, ?
            WHERE NOT EXISTS (
                SELECT 1 FROM opened_documents WHERE editor_id = ? AND document_id = ?
            )
            """,
            (editor_id, document.id, editor_id, document.id),
        )
    return document


def select_document(conn, editor_id, document_id):
    with conn:
        conn.execute(
            "UPDATE editors SET active_tab = ? WHERE id = ?", (document_id, editor_id)
        )


def close_document(conn, editor_id, document_id):
    """Closes the tab, selecting the last remaining tab if it was active"""
    editor = get_editor(conn, editor_id)
    was_active = editor.active_document and editor.active_document.id == document_id

    with conn:
        conn.execute(
            "DELETE FROM opened_documents WHERE editor_id = ? AND document_id = ?",
            (editor_id, document_id),
        )
    delete_document(conn, document_id)

    if was_active:
        remaining = [d for d in editor.documents if d.id != document_id]
        select_document(conn, editor_id, remaining[-1].id if remaining else None)


# Views

bp = Blueprint("editor", __name__)


def editor_or_404(id):
    found = get_editor(get_db(), id)
    if found is None:
        abort(404)
    return found


def document_or_404(id):
    found = get_document(get_db(), id)
    if found is None:
        abort(404)
    return found


@bp.route("<id>/tabs", methods=["GET"])
def tabs(id):
    editor = editor_or_404(id)

    return make_response(
        render_template(
            "partials/tabs.html", editor=editor, document=editor.active_document
        )
    )


@bp.route("<id>/tabs/<document_id>", methods=["POST"])
def update_tabs(id, document_id):
    action = request.args.get("action")
    triggers = {"tab-action": action}

    editor = editor_or_404(id)
    document = document_or_404(document_id)

    if action in ["select"]:
        if editor.active_document != document:
            triggers["editor-content-update"] = True
        select_document(get_db(), editor.id, document.id)
    elif action == "close":
        if editor.active_document == document:
            triggers["editor-content-update"] = True
        close_document(get_db(), editor.id, document.id)
    else:
        abort(404)

    resp = tabs(id)
    resp.headers["Hx-Trigger"] = json.dumps(triggers)
    return resp


visual_editors = {"application/rvt+edn": "partials/editor_rvt.html"}


@bp.route("<id>/content", methods=["GET"])
def content(id):
    editor = editor_or_404(id)
    active_document = editor.active_document
    testcase = None

    if not active_document:
        return make_response("")

    supports_visual = active_document.mime in visual_editors
    raw = active_document.meta.get("raw", False)

    if raw:
        template = "partials/editor.html"
    elif active_document.mime == "application/rvt+edn":
        template = visual_editors[active_document.mime]
        testcase = EdnTestCase(active_document.path.name, active_document.content)
    else:
        template = "partials/editor.html"

    return render_template(
        template,
        id=id,
        editor=editor,
        documents=editor.documents,
        document=active_document,
        raw=raw,
        supports_visual=supports_visual,
        testcase=testcase,
    )


testcase_sections = ["title", "description", "requirements", "setup"]


@bp.route("<id>/content-section", methods=["GET"])
def section(id):
    section = int(request.args.get("section", -1))
    updated = int(request.args.get("updated", -1))
    edit = bool(request.args.get("edit", False))

    editor = editor_or_404(id)
    document = editor.active_document
    testcase = EdnTestCase(document.path.name, document.content)

    if section == -1:  # add new section
        testcase.statements.append("")

    if edit:
        template = "partials/editor_rvt_section_edit.html"
    else:
        template = "partials/editor_rvt_section.html"

    return render_template(
        template,
        id=id,
        editor=editor,
        testcase=testcase,
        document=document,
        section=section,
        sections=[section if updated == -1 else updated],
    )


@bp.route("<id>/content/<document_id>", methods=["POST"])
def update_content(id, document_id):
    action = request.args.get("action")

    conn = get_db()
    document = document_or_404(document_id)
    triggers = set()

    if action == "save":
        save_document(conn, document)
        triggers.add("tab-action")
    elif action == "save-draft":
        content = request.form["value"]
        save_draft(conn, document, content)
        triggers.add("tab-action")
    elif action == "view-raw":
        set_meta(conn, document, "raw", True)
        triggers.add("editor-content-update")
    elif action == "view-visual":
        set_meta(conn, document, "raw", False)
        triggers.add("editor-content-update")
    else:
        abort(404)

    resp = make_response("SUCCESS", 200)
    resp.headers["Hx-Trigger"] = json.dumps({k: True for k in triggers})
    return resp


@bp.route("<id>/content/<document_id>", methods=["PATCH"])
def update_testcase(id, document_id):
    section = int(request.args.get("section"))
    value = request.form.get("value")

    editor = editor_or_404(id)
    document = document_or_404(document_id)
    testcase = EdnTestCase(document.path.name, document.content)

    triggers = {"tab-action": "save-draft"}

    modified, shifted = testcase.update_statement(section, value)
    save_draft(get_db(), document, testcase.text)

    triggers["updated-section"] = {"updated": {o: n for o, n in shifted}}

    template = "partials/editor_rvt_section.html"
    resp = make_response(
        render_template(
            template,
            id=id,
            editor=editor,
            testcase=testcase,
            document=document,
            sections=modified,
        )
    )
    resp.headers["Hx-Trigger"] = json.dumps(triggers)
    return resp


@bp.route("<id>/run_test/<document_id>", methods=["POST"])
def run_test(id, document_id):
    q = sqlqueue.SQLPriorityQueue(get_db())
    document = document_or_404(document_id)

    # This is where we would actually create a job
    # jobqueue.Job(client_id, body)
    # framework.TestJob(body, client_id=None, content_type='automationv3/edn')
    # framework.BatchTestJob(
    #    [TestJob(body1),
    #     TestJob(body2),
    #     TestJob(body3)], client_id=client_id, content_type='automationv3/edn')
    job = {
        "Content-Type": edn.Keyword("edn", namespace="automationv3"),
        "body": document.content,
    }

    q.put(edn.writes(job))

    return make_response("SUCCESS", 200)
