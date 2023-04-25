import sqlite3
from pathlib import Path

class TreeviewRepository:
    def __init__(self, workspace_id, dbpath):
        self.workspace_id = workspace_id
        self._dbpath = dbpath
        self._conn = sqlite3.connect(dbpath)

        # Determine if table exists
        cursor = self._conn.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name='workspace_treeview_open'
        """)
        if len(cursor.fetchall()) == 0:
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

class WorkspaceRepository:
    def __init__(self, id, dbpath):
        self.id = id
        self._dbpath = dbpath
        self._conn = sqlite3.connect(dbpath)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS workspace_tabs (
                path TEXT PRIMARY KEY,
                text TEXT NOT NULL
            )
        """)
        self._conn.commit()

        self.treeview = TreeviewRepository(id, dbpath)

    def get_file(self, path):
        cursor = self._conn.execute("""
            SELECT text
            FROM workspace_files
            WHERE id = ?
        """, (path,))
        row = cursor.fetchone()
        return row[0] if row else ""
    
    def update_file(self, path, text):
        cursor = self._conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO workspace_files (path, text) VALUES (?, ?)",
                (path, text)
            )
        except sqlite3.IntegrityError:
            cursor.execute(
                "UPDATE requirements SET text = ? WHERE path = ?",
                (text, path)
            )
        self._conn.commit()
        cursor.close()


