import sqlite3
import json
from pathlib import Path
from functools import wraps

# Helpers

def is_binary(path, sample_length=8000):
    '''Simplistic Git method. Basically read checking for NUL'''
    try:
        with path.open(mode='r') as f:
            f.read(sample_length)
        return False
    except UnicodeDecodeError:
        pass
    return True

def table_exists(conn, table_name):
    cursor = conn.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name= ?
    """, (table_name,))
    return len(cursor.fetchall()) != 0

class Treeview:
    
    def __init__(self, conn, workspace_id):
        self.conn = conn
        self.workspace_id = workspace_id

    def toggle_node(self, path):
        opened = self.opened

        if path in opened:
            opened.remove(path)
        else:
            opened.append(path)

        self.opened = opened
        return opened

    @property
    def opened(self):
        cursor = self.conn.execute("""
            SELECT opened_treeview_nodes
            FROM workspaces
            WHERE id = ? 
        """, (self.workspace_id,))
        row = cursor.fetchone()
        if row is None:
            return []

        result = [Path(p) for p in json.loads(row[0])]
        return result

    @opened.setter
    def opened(self, val):
        opened_as_str = [str(p) for p in val]
        cursor = self.conn.cursor()
        cursor.execute(""" 
            UPDATE workspaces 
            SET opened_treeview_nodes = ?
            WHERE id = ?
        """, (json.dumps(opened_as_str), self.workspace_id))
        self.conn.commit()
        cursor.close()

def when_open(f):
    @wraps(f)
    def wrapper(self, *args, **kwargs):
        if not self.is_opened:
            print(f"WARNING: Trying to call {f.__name__} when Document is closed")
            return
        f(self, *args, **kwargs)
    return wrapper

def when_closed(f):
    @wraps(f)
    def wrapper(self, *args, **kwargs):
        if self.is_opened:
            print(f"WARNING: Trying to call {f.__name__} when Document is open")
            return
        f(self, *args, **kwargs)
    return wrapper

class Document:
    def __init__(self, conn, path, root, is_opened, editor_id):
        self.conn = conn
        self.path = path
        self.root = root
        self.is_opened = is_opened
        self.editor_id = editor_id

        # Persisted Fields read once
        self._read = False
        self._st_mtime = None
        self._mime = None
        self._draft = None
        self._rank = None

    @when_open
    def read_db(self):
        if self._read:
            return

        cursor = self.conn.execute("""
            SELECT draft, mime, st_mtime, rank
            FROM documents
            WHERE path = ? and editor_id = ?
        """, (str(self.path), self.editor_id))
        row = cursor.fetchone()
        draft, mime, st_mtime, rank = row
        self._draft, self._mime, self._st_mtime, self._rank = row
        self._read = True

    @property
    def st_mtime(self):
        self.read_db()
        return self._st_mtime

    @property
    def mime(self):
        self.read_db()
        return self._mime

    @property
    def draft(self):
        self.read_db()
        return self._draft

    @property
    def rank(self):
        self.read_db()
        return self._rank

    @property
    def path_on_disk(self):
        return self.root / self.path

    @when_closed
    def open(self):
        '''Opens document into workspace'''

        st_mtime = self.path_on_disk.stat().st_mtime

        # TODO: Improve
        if is_binary(self.path_on_disk):
            mime = 'application/octet-stream'
            content = 'BINARY FILE'
        else:
            mime = 'text/plain'
            content = self.path_on_disk.read_text()

        cursor = self.conn.cursor()
        cursor.execute(""" 
            INSERT INTO documents(path, mime, st_mtime, rank, editor_id) 
            VALUES (?, ?, ?, (SELECT IFNULL(MAX(rank),0)+1 FROM documents), ?)
        """, (str(self.path), mime, st_mtime, self.editor_id))
        self.conn.commit()
        cursor.close()
        
        self.is_opened = True
        return content

    @when_open
    def save(self, content):
        '''Writes content to disk, clears draft and updates st_mtime'''
        
        if isinstance(content, str):
            self.path_on_disk.write_text(content)
        else:
            # Nothing to save for now
            pass
        
        st_mtime = self.path_on_disk.stat().st_mtime
        
        cursor = self.conn.cursor()
        cursor.execute(""" 
            UPDATE documents
            SET draft = ?, st_mtime = ?
            WHERE path = ? and editor_id = ?
        """, (None, st_mtime, str(self.path), self.editor_id))
        self.conn.commit()
        cursor.close()

        self._draft = None
        self._st_mtime = st_mtime

    @when_open
    def save_draft(self, content):
        cursor = self.conn.cursor()
        cursor.execute(""" 
            UPDATE documents
            SET draft = ?
            WHERE path = ? and editor_id = ?
        """, (content, str(self.path), self.editor_id))
        self.conn.commit()
        cursor.close()

        self._draft = content

    @property
    def content(self):
        if self.draft is not None:
            return self.draft

        if self.mime == 'text/plain':
            return self.path_on_disk.read_text()
        else:
            return 'BINARY CONTENT'
            
    def is_modified(self):
        return self.draft is not None

    def modified_since_opened(self):
        '''Returns true if underlying file has changed on disk
           since being opened
        '''
        return self.st_mtime != self.path_on_disk.stat().st_mtime
    
    def close(self):
        self.conn.execute("""
            DELETE FROM documents 
            WHERE path = ? and editor_id = ?
        """, (str(self.path), self.editor_id))
        self.conn.commit()

        self.is_opened = False
        self._read = False

    def __eq__(self, other):
        return self.path == other

    def __hash__(self):
        return hash(self.path)

class Editor:
    @staticmethod
    def ensure_db(conn):
        if not table_exists(conn, 'editors'):
            conn.execute("""
                CREATE TABLE IF NOT EXISTS editors(
                    id INTEGER PRIMARY KEY,
                    active_tab TEXT,
                    workspace_id TEXT NOT NULL,
                    FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
                )
            """)
            conn.commit()
        if not table_exists(conn, 'documents'):
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents(
                    id INTEGER PRIMARY KEY,
                    path TEXT,
                    draft TEXT,
                    mime TEXT NOT NULL,
                    st_mtime REAL, 
                    rank INTEGER NOT NULL,
                    editor_id INTEGER NOT NULL,
                    UNIQUE(path, editor_id),
                    FOREIGN KEY(editor_id) REFERENCES editors(id)
                )
            """)
            conn.commit()

    def __init__(self, id, conn, workspace_id, root):
        self.id = id
        self._conn = conn
        self.workspace_id = workspace_id
        self.root = root

        # need to figure out what to do about
        # deleted files
        # for now just clean up documents that no longer exists
        for document in self.documents():
            if not document.path_on_disk.exists():
                document.close()

    @staticmethod
    def create(conn, workspace_id, root):
        cursor = conn.cursor()
        cursor.execute(""" 
            INSERT INTO editors(workspace_id) 
            VALUES (?)
        """, (workspace_id,))
        id = cursor.lastrowid
        conn.commit()
        cursor.close()

        return Editor(id, conn, workspace_id, root)


    def documents(self, path=None):
        cursor = self._conn.execute("""
            SELECT path
            FROM documents
            WHERE editor_id = ?
            ORDER BY rank ASC
        """, (self.id,))
        rows = cursor.fetchall()
        document_paths = [Path(p[0]) for p in rows]

        if path is None:
            return [Document(self._conn, path, self.root, is_opened=True, editor_id=self.id)
                    for path in document_paths]
        else:
            is_opened = path in document_paths
            return Document(self._conn, path, self.root, is_opened, editor_id=self.id)

    @property
    def active_document(self):
        cursor = self._conn.execute("""
            SELECT active_tab 
            FROM editors
            WHERE id = ?
        """, (self.id,))
        row = cursor.fetchone()
        active = row[0]
        if active is not None:
            document = self.documents(Path(active))
            if document.is_opened and document.path_on_disk.exists():
                return document
            else: # just return the first document
                documents = self.documents()
                if len(documents) > 0:
                    self.select_document(documents[0])
                    return documents[0]
        return None

    def select_document(self, document):
        cursor = self._conn.cursor()
        cursor.execute(""" 
            UPDATE editors
            SET active_tab = ?
            WHERE id = ?
        """, (str(document.path) if document is not None else None, self.id))
        self._conn.commit()
        cursor.close()

class Workspace:
    @staticmethod
    def ensure_db(conn):
        if not table_exists(conn, 'workspaces'):
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workspaces(
                    id TEXT PRIMARY KEY,
                    opened_treeview_nodes TEXT NOT NULL
                )
            """)
            conn.commit()
        Editor.ensure_db(conn)


    def __init__(self, id, conn, workspace_root):
        self.id = id
        self.conn = conn
        self.root = workspace_root

        self.ensure_self()
        self.treeview = Treeview(self.conn, self.id)

    def ensure_self(self):
        cursor = self.conn.execute(""" 
            SELECT COUNT(*)
            FROM workspaces
            WHERE id = ?
        """, (self.id,))
        row = cursor.fetchone()
        workspace_exists = row[0] == 1 

        if not workspace_exists:
            cursor = self.conn.cursor()
            cursor.execute(""" 
                INSERT INTO workspaces(id, opened_treeview_nodes) 
                VALUES (?, ?)
            """, (self.id, json.dumps([])))
            self.conn.commit()
            cursor.close()

            # Create editor
            Editor.create(self.conn, self.id, self.root)

    def editors(self, id=None):
        if id is not None:
            return Editor(id, self.conn, self.id, self.root)

        # return first editor
        cursor = self.conn.execute(""" 
            SELECT id 
            FROM editors
            WHERE workspace_id = ?
        """, (str(self.id),))
        row = cursor.fetchone()
        return Editor(row[0], self.conn, self.id, self.root)
        


