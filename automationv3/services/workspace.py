"""Workspaces: the rvts directory of each git worktree, as a file tree"""

import io
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


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


# Checked in and in work. A workspace's files on disk may have edits that
# aren't committed: scratch runs use them as they are, reports only what
# is checked in (the branch's HEAD).


def git(root, *args, binary=False):
    """The output of git, run in `root`"""
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=True)
    return result.stdout if binary else result.stdout.decode("utf-8")


def head_commit(root):
    """The commit checked out at `root`, or None if there is none yet"""
    try:
        return git(root, "rev-parse", "--verify", "-q", "HEAD").strip() or None
    except subprocess.CalledProcessError:
        return None


def edited_files(root):
    """Paths (relative to `root`) whose files differ from what is checked
    in: modified, staged, deleted or new"""
    if head_commit(root) is None:
        changed = ""
    else:
        changed = git(root, "diff", "--name-only", "--relative", "-z", "HEAD", "--", ".")
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z", "--", ".")
    return {p for p in (changed + untracked).split("\0") if p}


def committed_text(root, path):
    """The checked-in text of `path` (relative to `root`), or None if it
    isn't checked in"""
    try:
        return git(root, "show", f"HEAD:./{PurePosixPath(path)}")
    except subprocess.CalledProcessError:
        return None


def checked_in(root, cache):
    """A folder holding `root` as it is checked in (at HEAD), kept under
    `cache` by commit so it is written once. Raises ValueError if nothing
    is checked in yet."""
    commit = head_commit(root)
    if commit is None:
        raise ValueError(f"{root}: nothing is checked in yet")
    prefix = git(root, "rev-parse", "--show-prefix").strip()
    out = Path(cache) / f"{commit}-{prefix.strip('/').replace('/', '_') or 'root'}"
    if out.is_dir():
        return out
    Path(cache).mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="checkout-", dir=cache))
    try:
        # Run in `root`, archive holds just its folder, paths relative to it
        archive = git(root, "archive", "--format=tar", commit, binary=True)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            if hasattr(tarfile, "data_filter"):  # Python 3.12, and fixes back to 3.8
                tar.extractall(work, filter="data")
            else:
                tar.extractall(work)
        try:
            os.replace(work, out)
        except OSError:
            if not out.is_dir():  # not another request writing it first
                raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out
