import hashlib
from dataclasses import dataclass, field
import json
from pathlib import Path
import mimetypes

from ...framework import edn


def is_binary(path, sample_length=8000):
    """Simplistic Git method. Basically read checking for NUL"""
    try:
        with path.open(mode="r") as f:
            f.read(sample_length)
        return False
    except UnicodeDecodeError:
        pass
    return True


def guess_mime(path):
    # TODO: Improve
    if is_binary(path):
        mime = "application/octet-stream"
    elif path.suffix == ".rvt":
        content = path.read_text()
        try:
            parsed_content = edn.read(content)
            if isinstance(parsed_content, (str, edn.List)):
                mime = "application/rvt+edn"
            else:
                mime = "application/rvt"
        except Exception:
            mime = "application/rvt"
    else:
        mime = mimetypes.guess_type(path)[0]
    return mime


@dataclass(eq=False)
class Document:
    """A file opened for editing. `draft` holds unsaved content."""

    id: str
    path: Path
    mime: str
    st_mtime: float
    draft: str = None
    meta: dict = field(default_factory=dict)

    @property
    def content(self):
        if self.draft is not None:
            return self.draft

        if self.mime == "application/octet-stream":
            return "BINARY CONTENT"
        else:
            return self.path.read_text()

    def is_modified(self):
        return self.draft is not None

    def modified_since_opened(self):
        """Returns true if underlying file has changed on disk
        since being opened
        """
        return self.st_mtime != self.path.stat().st_mtime

    def __eq__(self, other):
        return isinstance(other, Document) and self.id == other.id

    def __hash__(self):
        return hash(self.id)


def document_from_row(row):
    id, path, mime, st_mtime, draft, meta = row
    return Document(id, Path(path), mime, st_mtime, draft, json.loads(meta))


def get_document(conn, id):
    row = conn.execute(
        "SELECT id, path, mime, st_mtime, draft, meta FROM documents WHERE id = ?",
        (id,),
    ).fetchone()
    return document_from_row(row) if row else None


def all_documents(conn):
    rows = conn.execute("SELECT id, path, mime, st_mtime, draft, meta FROM documents")
    return [document_from_row(row) for row in rows]


def open_document(conn, path):
    """The document for `path`, recording it as opened if it isn't already"""
    path = path.resolve()
    id = hashlib.sha1(str(path).encode("utf-8")).hexdigest()

    document = get_document(conn, id)
    if document is None:
        document = Document(id, path, guess_mime(path), path.stat().st_mtime)
        with conn:
            conn.execute(
                """
                INSERT INTO documents(id, path, mime, st_mtime, meta)
                VALUES (?, ?, ?, ?, ?)
                """,
                (id, str(path), document.mime, document.st_mtime, json.dumps({})),
            )
    return document


def delete_document(conn, id):
    with conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (id,))


def save_document(conn, document):
    """Writes content to disk, clears draft and updates st_mtime"""
    if document.mime != "application/octet-stream":
        document.path.write_text(document.content)

    document.draft = None
    document.st_mtime = document.path.stat().st_mtime
    with conn:
        conn.execute(
            "UPDATE documents SET draft = NULL, st_mtime = ? WHERE id = ?",
            (document.st_mtime, document.id),
        )


def save_draft(conn, document, content):
    document.draft = content
    with conn:
        conn.execute(
            "UPDATE documents SET draft = ? WHERE id = ?", (content, document.id)
        )


def set_meta(conn, document, key, val):
    document.meta[key] = val
    with conn:
        conn.execute(
            "UPDATE documents SET meta = ? WHERE id = ?",
            (json.dumps(document.meta), document.id),
        )
