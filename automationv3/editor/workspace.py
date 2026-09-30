from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
import subprocess

from .treeviews import FileNode


@dataclass
class Workspace:
    """A git worktree's rvts directory, named by its branch"""

    id: str
    root: Path
    editor_id: int

    @cached_property
    def root_node(self):
        return FileNode(self.root)


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


def get_workspace(conn, id, root):
    """The workspace `id`, creating it (and its editor) on first use"""
    row = conn.execute(
        "SELECT editor_id FROM workspaces WHERE id = ?", (id,)
    ).fetchone()
    if row is not None:
        return Workspace(id, root, row[0])

    with conn:
        editor_id = conn.execute(
            "INSERT INTO editors(active_tab) VALUES (NULL)"
        ).lastrowid
        conn.execute(
            "INSERT INTO workspaces(id, editor_id) VALUES (?, ?)", (id, editor_id)
        )
    return Workspace(id, root, editor_id)
