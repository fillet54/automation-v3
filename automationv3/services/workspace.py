"""Workspaces: the rvts directory of each git worktree, as a file tree"""

import subprocess
from pathlib import Path


class FileNode:
    """A file or directory within a root directory.

    Every node keeps a reference to its root node and refuses to be
    created for a path outside of that root."""

    def __init__(self, path, root=None):
        if root is None:
            self.root = self
            self.path = Path(path).resolve()
        else:
            self.root = root
            self.path = (root.path / path).resolve()
            if not self.path.is_relative_to(root.path):
                raise ValueError(f"'{self.path}' is not within '{root.path}'")

    def children(self):
        return [FileNode(child, self.root) for child in self.path.iterdir()]

    @property
    def name(self):
        return self.path.name

    @property
    def relative_path(self):
        return self.path.relative_to(self.root.path)

    @property
    def is_root(self):
        return self.path == self.root.path

    def is_dir(self):
        return self.path.is_dir()

    def is_file(self):
        return self.path.is_file()

    def __eq__(self, other):
        if isinstance(other, FileNode):
            return self.path == other.path
        return self.path == Path(other)

    def __hash__(self):
        return hash(self.path)

    def __lt__(self, other):
        return self.path < other.path

    def __str__(self):
        return str(self.path)

    def __repr__(self):
        return f"FileNode('{self.path}')"


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


def is_binary(path, sample_length=8000):
    """True if `path` doesn't read as text"""
    try:
        with path.open(mode="r") as f:
            f.read(sample_length)
        return False
    except UnicodeDecodeError:
        return True
