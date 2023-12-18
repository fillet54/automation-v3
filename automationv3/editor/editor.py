from contextlib import closing

from .document import Document
from ..database import get_db


# Helpers
def table_exists(conn, table_name):
    cursor = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name= ?
    """,
        (table_name,),
    )
    return len(cursor.fetchall()) != 0


class Editor:
    @staticmethod
    def ensure_db(conn):
        Document.ensure_db(conn)

        if not table_exists(conn, "editors"):
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS editors(
                    id INTEGER PRIMARY KEY,
                    active_tab TEXT
                )
            """
            )
            conn.commit()
        if not table_exists(conn, "opened_documents"):
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS opened_documents(
                    id INTEGER PRIMARY KEY,
                    editor_id INTEGER REFERENCES editors(id) ON DELETE CASCADE,
                    document_id TEXT REFERENCES document(id) ON DELETE CASCADE
                )
            """
            )
            conn.commit()

    def __init__(self, conn, id):
        self.id = id
        self.conn = conn

    @staticmethod
    def create(conn):
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO editors(active_tab)
            VALUES (?)
        """,
            (None,),
        )
        id = cursor.lastrowid
        conn.commit()
        cursor.close()

        return Editor(conn, id)

    def documents(self):
        cursor = self.conn.execute(
            """
            SELECT document_id
            FROM opened_documents
            WHERE editor_id = ?
        """,
            (self.id,),
        )
        rows = cursor.fetchall()

        return [Document(self.conn, row[0]) for row in rows]

    @property
    def active_document(self):
        cursor = self.conn.execute(
            """
            SELECT active_tab
            FROM editors
            WHERE id = ?
        """,
            (self.id,),
        )
        row = cursor.fetchone()
        document_id = row[0]
        if document_id is not None:
            document = Document(self.conn, document_id)
            if document.path and document.path.exists():
                return document
            else:  # just return the first document
                documents = self.documents()
                if len(documents) > 0:
                    self.select_document(documents[0])
                    return documents[0]
        return None

    def select_document(self, document):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE editors
            SET active_tab = ?
            WHERE id = ?
        """,
            (document.id if document is not None else None, self.id),
        )
        self.conn.commit()
        cursor.close()

    def open(self, path):
        document = Document.open(self.conn, path)

        if document not in self.documents():
            with closing(self.conn.cursor()) as c:
                c.execute(
                    """
                    INSERT OR REPLACE INTO opened_documents(editor_id, document_id)
                    VALUES (?, ?)
                """,
                    (self.id, document.id),
                )
                self.conn.commit()
        return document

    def close(self, document):
        change_active = self.active_document == document

        # Remove from editor
        with closing(self.conn.cursor()) as c:
            c.execute(
                """
                DELETE FROM opened_documents
                WHERE document_id = ?
            """,
                (document.id,),
            )
            self.conn.commit()

        # close document
        document.close()

        if change_active:
            documents = self.documents()
            self.select_document(documents[-1] if len(documents) > 0 else None)


def get_editor(id):
    if id is not None:
        conn = get_db()
        return Editor(conn, id)
    return None
