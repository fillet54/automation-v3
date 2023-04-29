import sqlite3
import json
from pathlib import Path
from functools import wraps

def table_exists(conn, table_name):
    cursor = conn.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name= ?
    """, (table_name,))
    return len(cursor.fetchall()) != 0

class WorkspaceState:
    @staticmethod
    def ensure_db(conn):
        if not table_exists(conn, 'workspace_state'):
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workspace_state(
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.commit()
    
    def __init__(self, conn):
        self._conn = conn

    def get(self, key):
        cursor = self._conn.execute("""
            SELECT value
            FROM workspace_state
            WHERE key = ?
        """, (key, ))
        result = cursor.fetchone()
        if result:
            return result[0]
        return None

    def put(self, key, val):
        cursor = self._conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO workspace_state(key, value) 
            VALUES (?, ?)
        """, (key, val))
        self._conn.commit()
        cursor.close()

    def get_json(self, key):
        val = self.get(key)
        if val:
            return json.loads(val)
        return None

    def put_json(self, key, val):
        val = json.dumps(val)
        self.put(key, val)

    def get_dict(self, key):
        return self.get_json(key) or {}

    def put_dict(self, key, val):
        self.put_json(key, val)
    
    def get_list(self, key):
        return self.get_json(key) or {}

    def put_list(self, key, val):
        self.put_json(key, val)


class Treeview:
    
    def __init__(self, conn, state):
        self._conn = conn
        self.state = state 

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
        return [Path(p) 
                for p in self.state.get_list('treeview.opened')]

    @opened.setter
    def opened(self, val):
        self.state.put_list('treeview.opened', [str(p) for p in val])

def when_open(f):
    @wraps(f)
    def wrapper(self, *args, **kwargs):
        if not self.is_opened:
            print(f"WARNING: Trying to call {f.__name__} when Document is open")
            return
        f(self, *args, **kwargs)
    return wrapper

def when_closed(f):
    @wraps(f)
    def wrapper(self, *args, **kwargs):
        if self.is_opened:
            print(f"WARNING: Trying to call {f.__name__} when Document is closed")
            return
        f(self, *args, **kwargs)
    return wrapper

class Document:
    def __init__(self, conn, path, root, is_opened):
        self.conn = conn
        self.path = path
        self.root = root
        self.is_opened = is_opened

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
            WHERE path = ?
        """, (str(self.path),))
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
        try:
            content = self.path_on_disk.read_text()
            mime = 'text/plain'
        except:
            content = None 
            mime = 'application/octet-stream'

        cursor = self.conn.cursor()
        cursor.execute(""" 
            INSERT INTO documents(path, mime, st_mtime, rank) 
            VALUES (?, ?, ?, (SELECT IFNULL(MAX(rank),0)+1 FROM documents))
        """, (str(self.path), mime, st_mtime))
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
            self.path_on_disk.write_bytes(content)
        
        st_mtime = self.path_on_disk.stat().st_mtime
        
        cursor = self.conn.cursor()
        cursor.execute(""" 
            UPDATE documents
            SET draft = ?, st_mtime = ?
            WHERE path = ?
        """, (None, st_mtime, str(self.path)))
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
            WHERE path = ?
        """, (content, str(self.path)))
        self.conn.commit()
        cursor.close()

        self._draft = content

    @property
    def content(self):
        if self.draft is not None:
            return self.draft

        # else read from disk
        if self.mime == 'application/octet-stream':
            return 'BINARY CONTENT'
        else:
            return self.path_on_disk.read_text()

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
            WHERE path = ?
        """, (str(self.path),))
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
        if not table_exists(conn, 'documents'):
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents(
                    path TEXT PRIMARY_KEY,
                    draft TEXT,
                    mime TEXT,
                    st_mtime REAL, 
                    rank INTEGER NOT NULL
                )
            """)
            conn.commit()

    def __init__(self, conn, state):
        self._conn = conn
        self.state = state 


    def documents(self, path=None):
        cursor = self._conn.execute("""
            SELECT path
            FROM documents
            ORDER BY rank ASC
        """)
        rows = cursor.fetchall()
        root = self.state.get('root')
        document_paths = [Path(p[0]) for p in rows]

        if path is None:
            return [Document(self._conn, path, root, is_opened=True)
                    for path in document_paths]
        else:
            is_opened = path in document_paths
            return Document(self._conn, path, root, is_opened)

    def active_document(self):
        active = self.state.get('active_document')
        if active is not None:
            return self.documents(Path(active))
        return None

    def select_document(self, document):
        self.state.put('active_document', str(document.path))

class Workspace:
    def __init__(self, conn, workspace_root):
        self._conn = conn

        # Initialize DBs
        WorkspaceState.ensure_db(conn)
        Editor.ensure_db(conn)

        self.state = WorkspaceState(conn)
        self.state.put('root', str(workspace_root))

        self.treeview = Treeview(self._conn, self.state)
        self.editor = Editor(conn, self.state)




