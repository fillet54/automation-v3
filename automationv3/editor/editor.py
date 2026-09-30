from dataclasses import dataclass, field

from .document import Document, open_document, delete_document, document_from_row


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
