"""Workspaces: the scripts folder of each git worktree, as a file tree

A workspace is named by its scripts folder in one worktree, anywhere in
the repository (its top, or a folder below it). Every other worktree of
the repository has its workspace in the same folder: git finds them.
"""

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


def scripts_folder(path):
    """Where `path` is in its git worktree: its folder relative to the
    worktree's top, with "/" between folders ("" for the top itself)"""
    return git(path, "rev-parse", "--show-prefix").strip().rstrip("/")


def find_worktrees(path):
    """Maps each branch checked out in the repository of `path` (a scripts
    folder in one of its worktrees) to the same folder in that branch's
    worktree. Branches whose worktree has no such folder are left out,
    as are worktrees on no branch."""
    path = Path(path)
    folder = scripts_folder(path)
    worktrees = {}
    for entry in git(path, "worktree", "list", "--porcelain").split("\n\n"):
        fields = dict(line.partition(" ")[::2] for line in entry.splitlines())
        branch = fields.get("branch", "")
        if "worktree" not in fields or not branch.startswith("refs/heads/"):
            continue  # a bare repository, or a detached HEAD
        root = Path(fields["worktree"]) / folder
        if root.is_dir():
            worktrees[branch[len("refs/heads/"):]] = root
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


# Workspace sources: where a server's branches and their files come from.
# Pages ask a source, never git, so a central server can mirror a remote
# (services/mirror.py) where a single-user server or a local client reads
# worktrees.


class LocalWorktrees:
    """The branches checked out as git worktrees of the repository whose
    scripts folder (in one of them) is `path`: each branch's scripts
    folder on disk (in work, edits included) and as checked in (its HEAD,
    extracted under `cache` by commit)"""

    editable = True  # files on disk may differ from what is checked in

    def __init__(self, path, cache):
        self.path = Path(path)
        self.cache = Path(cache)

    def branches(self):
        """branch -> its scripts folder on disk"""
        return find_worktrees(self.path)

    def root(self, name):
        """The scripts folder of branch `name` as it is on disk, or None"""
        return self.branches().get(name) if name else None

    def checked_in(self, name):
        """The scripts folder of branch `name` as checked in, or None for an unknown
        branch or one with nothing committed"""
        root = self.root(name)
        if root is None:
            return None
        try:
            return checked_in(root, self.cache)
        except ValueError:
            return None

    def edited(self, name):
        """Paths in branch `name` whose files differ from what is checked in"""
        root = self.root(name)
        return edited_files(root) if root else set()

    def committed_text(self, name, path):
        root = self.root(name)
        return committed_text(root, path) if root else None

    def commit(self, name):
        """The commit branch `name` has checked out, or None"""
        root = self.root(name)
        return head_commit(root) if root else None

    def refresh(self, name=None):
        """Worktrees are always current"""
        return None
