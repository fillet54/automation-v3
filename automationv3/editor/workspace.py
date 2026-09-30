from pathlib import Path
from contextlib import closing
import subprocess

from flask import current_app, abort

from .treeviews import Treeview, FileNode
from .editor import Editor

from ..database import get_db


class Workspace:
    def __init__(self, id, conn, workspace_root):
        self.id = id
        self.conn = conn

        # TODO: Should persist this to determine if a workspace is gone
        self.root = workspace_root

        self._editors = None
        self._filesystem_tree = None

        self.ensure_self()

    def ensure_self(self):
        cursor = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM workspaces
            WHERE id = ?
        """,
            (self.id,),
        )
        row = cursor.fetchone()
        workspace_exists = row[0] == 1

        if not workspace_exists:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO workspaces(id)
                VALUES (?)
            """,
                (self.id,),
            )
            self.conn.commit()
            cursor.close()

            # Create editor
            self._editors = [Editor.create(self.conn)]
            with closing(self.conn.cursor()) as c:
                c.execute(
                    """
                    INSERT INTO workspace_editors(workspace_id, editor_id)
                    VALUES (?, ?)
                """,
                    (self.id, self._editors[0].id),
                )
                self.conn.commit()

            # Create Filesystem Treeview
            self._filesystem_treeview = Treeview.create(
                self.conn, self.root, FileNode
            )
            with closing(self.conn.cursor()) as c:
                c.execute(
                    """
                    INSERT INTO workspace_treeviews(workspace_id, treeview_id, type)
                    VALUES (?, ?, 'filesystem')
                """,
                    (self.id, self._filesystem_treeview.id),
                )
                self.conn.commit()

    def editors(self, id=None):
        if id is not None:
            return Editor(self.conn, id)

        if self._editors is None:
            # return first editor
            cursor = self.conn.execute(
                """
                SELECT editor_id
                FROM workspace_editors
                WHERE workspace_id = ?
            """,
                (str(self.id),),
            )
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
            cursor = self.conn.execute(
                """
                SELECT treeview_id
                FROM workspace_treeviews
                WHERE workspace_id = ? AND type = 'filesystem'
            """,
                (self.id,),
            )
            row = cursor.fetchone()
            self._filesystem_tree = Treeview(self.conn, row[0], FileNode)
        return self._filesystem_tree


def find_worktrees(repo):
    """Maps each branch checked out in `repo` to its rvts directory"""
    output = subprocess.check_output(
        ["git", "worktree", "list", "--porcelain"], cwd=repo
    )
    output = output.decode("utf-8").splitlines()
    output = zip(output[::4], output[1::4], output[2::4], output[3::4])
    worktrees = {}
    for worktree, head, branch, _ in output:
        worktree_root = Path(worktree[len("worktree") + 1 :]) / "rvts"
        name = branch[len("branch refs/heads/") :]
        worktrees[name] = worktree_root
    return worktrees


def get_workspaces():
    worktrees = find_worktrees(current_app.config["WORKSPACE_PATH"])
    return [Workspace(id, get_db(), root) for id, root in worktrees.items()]


def get_workspace(id):
    """The workspace for branch `id`. A workspace id is a branch name of
    the git repo at WORKSPACE_PATH"""
    worktrees = find_worktrees(current_app.config["WORKSPACE_PATH"])
    if id not in worktrees:
        abort(404)
    return Workspace(id, get_db(), worktrees[id])
