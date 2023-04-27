import sqlite3
from pathlib import Path

def table_exists(conn, table_name):
    cursor = conn.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name= ?
    """, (table_name,))
    return len(cursor.fetchall()) != 0


class TreeviewRepository:
    def __init__(self, workspace_id, dbpath):
        self.workspace_id = workspace_id
        self._dbpath = dbpath
        self._conn = sqlite3.connect(dbpath)

        if not table_exists(self._conn, 'workspace_treeview_open'):
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS workspace_treeview_open (
                    id INTEGER PRIMARY KEY,
                    path TEXT,
                    workspace_id INTEGER NON NULL
                )
            """)
            self._conn.execute("""
                CREATE INDEX workspace_treeview ON workspace_treeview_open(workspace_id)
            """)
            self._conn.commit()

    def get_opened(self):
        cursor = self._conn.execute("""
            SELECT path
            FROM workspace_treeview_open
            WHERE workspace_id = ?
        """, (self.workspace_id, ))
        rows = cursor.fetchall()
        results = [Path(row[0]) for row in rows]
        return results

    def toggle_node(self, path):
        opened = self.get_opened()

        if path in opened:
            opened.remove(path)
            self.close_node(path)
        else:
            opened.append(path)
            self.open_node(path)
        return opened

    def open_node(self, path):
        cursor = self._conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO workspace_treeview_open(path, workspace_id) 
                VALUES (?, ?)
            """, (str(path), self.workspace_id))
        except sqlite3.IntegrityError:
            pass
        self._conn.commit()
        cursor.close()

    def close_node(self, path):
        cursor = self._conn.cursor()
        try:
            cursor.execute("""
                DELETE FROM workspace_treeview_open
                WHERE path = ? and workspace_id = ?
            """, (str(path), self.workspace_id))
        except sqlite3.IntegrityError:
            pass
        self._conn.commit()
        cursor.close()

class WorkspaceTabRepository:
    def __init__(self, workspace_id, dbpath):
        self.workspace_id = workspace_id
        self._dbpath = dbpath
        self._conn = sqlite3.connect(dbpath)
        if not table_exists(self._conn, 'workspace_tabs'):
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS workspace_tabs (
                    id INTEGER PRIMARY KEY,
                    path TEXT NOT NULL,
                    text TEXT NOT NULL,
                    active INTEGER NOT NULL,
                    rank INTEGER NOT NULL,
                    workspace_id INTEGER NOT NULL,
                    UNIQUE(path, workspace_id)
                )
            """)
            self._conn.execute("""
                CREATE INDEX workspace_tabs_idx ON workspace_tabs(path, workspace_id)
            """)
            self._conn.commit()

    def get(self, path):
        'Return tab content'
        cursor = self._conn.execute("""
            SELECT text
            FROM workspace_tabs
            WHERE path = ? AND workspace_id = ?
        """, (str(path), self.workspace_id))
        row = cursor.fetchone()
        return row[0] if row else ''

    def get_all(self):
        'Return tabs paths ordered how they should be left to right'
        cursor = self._conn.execute("""
            SELECT path, active
            FROM workspace_tabs
            WHERE workspace_id = ?
            ORDER BY rank ASC
        """, (self.workspace_id,))
        rows = cursor.fetchall()
        return [(Path(path), active)
                for path, active in rows]
    
    def create(self, path, content):
        tab_rank = self.get_tab_rank()
        cursor = self._conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO workspace_tabs(path, text, active, rank, workspace_id) 
                VALUES (?, ?, ?, ?, ?)
            """, (str(path), content, 0, tab_rank+1, self.workspace_id))
        except sqlite3.IntegrityError:
            pass
        self._conn.commit()
        cursor.close()

    def update(self, path, content):
        tab_count = self.get_tab_rank()
        cursor = self._conn.cursor()
        try:
            cursor.execute("""
                UPDATE workspace_tabs SET text = ?
                WHERE path = ? and workspace_id = ?
            """, (content, str(path), self.workspace_id))
        except sqlite3.IntegrityError:
            pass
        self._conn.commit()
        cursor.close()

    def delete(self, path):
        self._conn.execute("""
            DELETE FROM workspace_tabs 
            WHERE workspace_id = ? AND path = ?
        """, (self.workspace_id, str(path)))
        self._conn.commit()

    def set_active(self, path):
        cursor = self._conn.cursor()
        cursor.execute("""
            UPDATE workspace_tabs SET active = 0 
            WHERE  workspace_id = ?
        """, (self.workspace_id,))
        cursor.execute("""
            UPDATE workspace_tabs SET active = 1 
            WHERE  workspace_id = ? and path = ?
        """, (self.workspace_id, str(path)))
        self._conn.commit()
        cursor.close()

    def get_tab_rank(self):
        return self._conn.execute("""
            SELECT max(rank) 
            FROM workspace_tabs
            WHERE workspace_id = ?
        """, (self.workspace_id,)).fetchone()[0] or 0


class WorkspaceRepository:
    def __init__(self, id, dbpath):
        self.id = id
        self._dbpath = dbpath

        self.treeview = TreeviewRepository(id, dbpath)
        self.tabs = WorkspaceTabRepository(id, dbpath)



