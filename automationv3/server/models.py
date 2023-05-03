from flask import  current_app, g, abort
import sqlite3
from pathlib import Path
import subprocess

from ..models import Requirements, Workspace

def get_db():
    if 'sqlite_db' not in g:
        g.sqlite_db = sqlite3.connect(current_app.config['DB_PATH'])
    return g.sqlite_db

def get_requirements():
    conn = get_db()
    return Requirements(conn)

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

