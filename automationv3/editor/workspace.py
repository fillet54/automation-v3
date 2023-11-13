import sqlite3
import json
from pathlib import Path
from functools import wraps
from contextlib import closing
import subprocess

from flask import  current_app, abort

from .treeviews import Treeview, FilesystemTreeNode
from .editor import Editor
from .document import Document

from ..framework import edn
from ..database import get_db

# Helpers
def table_exists(conn, table_name):
    cursor = conn.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name= ?
    """, (table_name,))
    return len(cursor.fetchall()) != 0

class Workspace:
    @staticmethod
    def ensure_db(conn):
        Editor.ensure_db(conn)
        Treeview.ensure_db(conn)
        if not table_exists(conn, 'workspaces'):
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workspaces(
                    id TEXT PRIMARY KEY
                )
            """)
            conn.commit()
        if not table_exists(conn, 'workspace_editors'):
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workspace_editors(
                    id INTEGER PRIMARY KEY,
                    workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
                    editor_id INTEGER REFERENCES editors(id) ON DELETE CASCADE
                )
            """)
            conn.commit()
        if not table_exists(conn, 'workspace_treeviews'):
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workspace_treeviews(
                    id INTEGER PRIMARY KEY,
                    type TEXT,
                    workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
                    treeview_id INTEGER REFERENCES treeviews(id) ON DELETE CASCADE
                )
            """)
            conn.commit()
        
    def __init__(self, id, conn, workspace_root):
        self.id = id
        self.conn = conn

        # TODO: Should persist this to determine if a workspace is gone
        self.root = workspace_root

        self._editors = None
        self._filesystem_tree = None

        self.ensure_self()


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
                INSERT INTO workspaces(id) 
                VALUES (?)
            """, (self.id,))
            self.conn.commit()
            cursor.close()

            # Create editor
            self.editors = [Editor.create(self.conn)]
            with closing(self.conn.cursor()) as c:
                c.execute(""" 
                    INSERT INTO workspace_editors(workspace_id, editor_id) 
                    VALUES (?, ?)
                """, (self.id, self.editors[0].id))
                self.conn.commit() 

            # Create Filesystem Treeview
            self._filesystem_treeview = Treeview.create(self.conn, self.root, FilesystemTreeNode)
            with closing(self.conn.cursor()) as c:
                c.execute(""" 
                    INSERT INTO workspace_treeviews(workspace_id, treeview_id, type) 
                    VALUES (?, ?, 'filesystem')
                """, (self.id, self._filesystem_treeview.id))
                self.conn.commit() 

    def editors(self, id=None):
        if id is not None:
            return Editor(self.conn, id)
        
        if self._editors is None:
            # return first editor
            cursor = self.conn.execute(""" 
                SELECT editor_id
                FROM workspace_editors
                WHERE workspace_id = ?
            """, (str(self.id),))
            rows = cursor.fetchall()

            if rows is None:
               self._editors = [] 
            else:
                self._editors = [Editor(self.conn, row[0]) for row in rows]
        return self._editors

    def active_editor(self):
        return self.editors()[0]

    def filesystem_tree(self):
        if self._filesystem_tree is None:
            cursor = self.conn.execute(""" 
                SELECT treeview_id 
                FROM workspace_treeviews
                WHERE workspace_id = ? AND type = 'filesystem'
            """, (self.id,))
            row = cursor.fetchone()
            self._filesystem_tree = Treeview(self.conn, row[0], FilesystemTreeNode)
        return self._filesystem_tree
        

def get_workspaces(id=None):
    conn = get_db()
    root = current_app.config['WORKSPACE_PATH']

    # A workspace id is the branch name of the git repo pointed
    # to at the root
    output = subprocess.check_output(['git', 'worktree', 'list', '--porcelain'], cwd=root)
    output = output.decode('utf-8').splitlines()
    output = zip(output[::4], output[1::4], output[2::4], output[3::4])
    worktrees = {}
    for worktree, head, branch, _ in output:
        worktree_root = Path(worktree[len('worktree')+1:]) / 'rvts'
        name = branch[len('branch refs/heads/'):]
        worktrees[name] = worktree_root

    if id is None:
        return [Workspace(id, conn, worktree_root)
                for id, worktree_root in worktrees.items()]

    if id in worktrees:
        return Workspace(id, conn, worktrees[id])

    abort(404)
