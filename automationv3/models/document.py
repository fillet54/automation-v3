from contextlib import closing
import hashlib
import json
from pathlib import Path

from automationv3.framework import edn

def table_exists(conn, table_name):
    cursor = conn.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name= ?
    """, (table_name,))
    return len(cursor.fetchall()) != 0

def is_binary(path, sample_length=8000):
    '''Simplistic Git method. Basically read checking for NUL'''
    try:
        with path.open(mode='r') as f:
            f.read(sample_length)
        return False
    except UnicodeDecodeError:
        pass
    return True

def guess_mime(path):
    # TODO: Improve
    if is_binary(path):
        mime = 'application/octet-stream'
    elif path.suffix == '.rvt':
        content = path.read_text()
        try:
            parsed_content = edn.read(content)
            if isinstance(parsed_content, edn.Map):
                mime = 'application/rvt+edn'
            else:
                mime = 'application/rvt'
        except:
            mime = 'application/rvt'
    else:
        mime = 'text/plain'
    return mime

class Document:
    @staticmethod
    def ensure_db(conn):
        if not table_exists(conn, 'documents'):
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents(
                    id TEXT PRIMARY KEY,
                    path TEXT,
                    draft TEXT,
                    mime TEXT NOT NULL,
                    st_mtime REAL, 
                    meta TEXT NOT NULL
                )
            """)
            conn.commit()

    @staticmethod
    def open(conn, path):
        '''Opens a file is not already opened. Otherwised returns opened document'''
        path = path.resolve()
        id = hashlib.sha1(str(path).encode('utf-8')).hexdigest()

        # Determine if document is already opened
        cursor = conn.execute("""
            SELECT COUNT(*) 
            FROM documents
            WHERE id = ?
        """, (id,))
        exists = cursor.fetchone()[0] > 0
        if exists:
            return Document(conn, id)

        # Otherwise open document
        st_mtime = path.stat().st_mtime
        mime = guess_mime(path)
        meta = json.dumps({})

        with closing(conn.cursor()) as c:
            c.execute(""" 
                INSERT INTO documents(id, path, mime, st_mtime, meta) 
                VALUES (?, ?, ?, ?, ?)
            """, (id, str(path), mime, st_mtime, meta))
            conn.commit()

        return Document(conn, id)

    @staticmethod
    def all(conn):
        cursor = conn.execute("""
            SELECT id 
            FROM documents
        """)
        return [Document(conn, row[0]) for row in cursor.fetchall()]

    def __init__(self, conn, id):
        self.id = id
        self.conn = conn

        # Persisted Fields read once
        self._read = False
        self._path = None
        self._st_mtime = None
        self._mime = None
        self._draft = None
        self._meta = None

    def read_db(self):
        if self._read:
            return

        cursor = self.conn.execute("""
            SELECT path, draft, mime, st_mtime, meta
            FROM documents
            WHERE id = ?
        """, (self.id,))
        row = cursor.fetchone()
        if row is not None:
            self._path, self._draft, self._mime, self._st_mtime, self._meta = row
        else:
            self._path, self._draft, self._mime, self._st_mtime, self._meta = None, None, None, None, '[]'

        self._meta = json.loads(self._meta)
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
    def path(self):
        self.read_db()
        if self._path:
            return Path(self._path)

    @property
    def meta(self):
        self.read_db()
        return self._meta

    def set_meta(self, key, val):
        meta = self.meta
        meta[key] = val

        with closing(self.conn.cursor()) as c:
            c.execute(""" 
                UPDATE documents
                SET meta = ?
                WHERE id = ?
            """, (json.dumps(meta), self.id))
            self.conn.commit()

    def save(self):
        '''Writes content to disk, clears draft and updates st_mtime'''

        if self.mime != 'application/octet-stream':
            self.path.write_text(self.content)

        st_mtime = self.path.stat().st_mtime
        
        with closing(self.conn.cursor()) as c:
            c.execute(""" 
                UPDATE documents
                SET draft = ?, st_mtime = ?
                WHERE id = ?
            """, (None, st_mtime, self.id))
            self.conn.commit()

        self._draft = None
        self._st_mtime = st_mtime

    def save_draft(self, content):
        with closing(self.conn.cursor()) as c:
            c.execute(""" 
                UPDATE documents
                SET draft = ?
                WHERE id = ?
            """, (content, self.id))
            self.conn.commit()
        self._draft = content

    @property
    def content(self):
        if self.draft is not None:
            return self.draft

        if self.mime == 'application/octet-stream':
            return 'BINARY CONTENT'
        else:
            return self.path.read_text()
            
    def is_modified(self):
        return self.draft is not None

    def modified_since_opened(self):
        '''Returns true if underlying file has changed on disk
           since being opened
        '''
        return self.st_mtime != self.path.stat().st_mtime
    
    def close(self):
        self.conn.execute("""
            DELETE FROM documents 
            WHERE id = ?
        """, (self.id,))
        self.conn.commit()
        self._read = False

    def __eq__(self, other):
        "Lookup by relative paths"
        return self.path == other

    def __hash__(self):
        return hash(self.path)

