from pathlib import Path
from contextlib import closing
import json

def table_exists(conn, table_name):
    cursor = conn.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name= ?
    """, (table_name,))
    return len(cursor.fetchall()) != 0

class Treeview:
    def __init__(self, conn, id, factoryfn):
        self.conn = conn
        self.id = id
        self.factoryfn = factoryfn

        cursor = self.conn.execute("""
            SELECT opened, root 
            FROM treeviews 
            WHERE id = ? 
        """, (self.id,))
        row = cursor.fetchone()

        self.root = factoryfn(row[1], root=None)
        self.opened = [factoryfn(n, self.root) for n in json.loads(row[0])]

    @staticmethod
    def ensure_db(conn):
        if not table_exists(conn, 'treeviews'):
            conn.execute("""
                CREATE TABLE IF NOT EXISTS treeviews(
                    id INTEGER PRIMARY KEY,
                    opened TEXT,
                    root TEXT,
                    workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE
                )
            """)
            conn.commit()

    @staticmethod
    def create(conn, root, factoryfn):
        with closing(conn.cursor()) as c:
            c.execute(""" 
                INSERT INTO treeviews(opened, root)
                VALUES (?, ?)
            """, (json.dumps([]), str(root)))
            id = c.lastrowid
            conn.commit()
        return Treeview(conn, id, factoryfn)

    def node(self, id):
        return self.factoryfn(id, self.root)

    def toggle(self, node):
        if node in self.opened:
            self.opened.remove(node)
        else:
            self.opened.append(node)

        opened_as_str = [str(i) for i in self.opened]

        with closing(self.conn.cursor()) as c:
            c.execute(""" 
                UPDATE treeviews 
                SET opened = ?
                WHERE id = ?
            """, (json.dumps(opened_as_str), self.id))
            self.conn.commit()

class FilesystemTreeNode:
    def __init__(self, pathstr, root):
        self.root = root or self

        self.path = Path(pathstr)
        if not self.path.is_relative_to(self.root.path):
            self.path = (self.root.path / Path(pathstr)).resolve()

    def children(self):
        return [FilesystemTreeNode(path, self.root)
                for path in self.path.iterdir()]

    @property
    def name(self):
        return self.path.name

    @property
    def relative_path(self):
        return self.path.relative_to(self.root.path)

    @property
    def is_root(self):
        return self.relative_path == Path('.')
    
    def is_dir(self):
        return self.path.is_dir()
    
    def is_file(self):
        return self.path.is_file()

    def __eq__(self, other):
        if isinstance(other, FilesystemTreeNode):
            return str(self.relative_path) == str(other.relative_path)
        else:
            return str(self.relative_path) == str(other) or str(self.path) == str(other)

    def __str__(self):
        return str(self.path)

    def __hash__(self):
        return hash(str(self.relative_path))

    def __gt__(self, other):
        return str(self) > str(other)
    
    def __lt__(self, other):
        return str(self) < str(other)

