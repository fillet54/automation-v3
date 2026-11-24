"""A central server's workspaces: a mirror of the team's git remote

The server keeps a bare `git clone --mirror` of the remote and shows every
branch at its tip. Nothing is edited on the server, so every file is
checked in: a branch's files are its tip's scripts folder (`scripts`, a
path in the repository; "" for its top), extracted once per commit under
the cache. The mirror is fetched when the git host's webhook
says something was pushed, and again before a report is queued, so a
report never runs a stale commit (see web/hooks.py and web/jobs.py).

Same interface as services.workspace.LocalWorktrees.

Reading the mirror (its branches, a file, a commit's scripts folder) is
done in process with libgit2 (services/repo.py); cloning and fetching
stay with the git command, which has the user's credential helpers and
SSH setup, and only run when something was pushed.
"""

import shutil
import subprocess
import threading
from pathlib import Path, PurePosixPath

import pygit2

from . import repo as gitrepo
from .util import git as run_git


class MirrorError(RuntimeError):
    pass


class MirrorTimeout(MirrorError):
    """git took too long: says nothing about what the repository holds"""


class MirrorWorkspaces:
    editable = False  # what the server shows is what was pushed

    def __init__(self, remote, path, cache, scripts=""):
        self.remote = remote
        self.scripts = str(PurePosixPath(scripts)).strip("/") if scripts else ""
        self.path = Path(path)
        self.cache = Path(cache)
        self.lock = threading.Lock()

    def git(self, *args, binary=False, check=True):
        try:
            return run_git(self.path, *args, binary=binary, timeout=300)
        except subprocess.CalledProcessError as e:
            if not check:
                return e.stdout if binary else e.stdout.decode(errors="replace")
            raise MirrorError(
                f"git {' '.join(args)}: {e.stderr.decode(errors='replace').strip()}"
            ) from None
        except subprocess.TimeoutExpired:
            raise MirrorTimeout(f"git {' '.join(args)}: timed out") from None

    def ensure(self):
        """Clone the remote if there is no mirror yet"""
        if (self.path / "HEAD").exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(["git", "clone", "--mirror", "--quiet", self.remote,
                                 str(self.path)], capture_output=True, timeout=600)
        if result.returncode != 0:
            shutil.rmtree(self.path, ignore_errors=True)
            raise MirrorError(f"Can't clone {self.remote}: "
                              f"{result.stderr.decode(errors='replace').strip()}")

    def refresh(self, name=None):
        """Fetch every branch from the remote (deleted ones go too)"""
        with self.lock:
            self.ensure()
            self.git("remote", "update", "--prune")

    def repository(self):
        """The mirror, opened for one question (see services/repo.py)"""
        try:
            return pygit2.Repository(str(self.path))
        except pygit2.GitError as e:
            raise MirrorError(f"{self.path}: {e}") from None

    def commits(self):
        """branch -> the commit at its tip"""
        if not (self.path / "HEAD").exists():
            return {}
        found = {}
        repository = self.repository()
        for name in repository.references:
            if not name.startswith("refs/heads/"):
                continue
            try:
                found[name[len("refs/heads/"):]] = str(repository.references[name].resolve().target)
            except (KeyError, pygit2.GitError):
                continue  # a symbolic ref to nothing
        return found

    def commit(self, name):
        return self.commits().get(name) if name else None

    def branches(self):
        """branch -> its scripts folder at its tip (branches without one are left out)"""
        found = {}
        for name, commit in sorted(self.commits().items()):
            root = self.extract(commit)
            if root is not None:
                found[name] = root
        return found

    def root(self, name):
        commit = self.commit(name)
        return self.extract(commit) if commit else None

    checked_in = root  # on the server, the files are what was pushed

    def edited(self, name):
        return set()

    def committed_text(self, name, path):
        commit = self.commit(name)
        if commit is None:
            return None
        return gitrepo.file_text(self.repository(), commit, PurePosixPath(self.scripts, path))

    def extract(self, commit):
        """The scripts folder of `commit`, extracted once under the cache;
        None if the commit has none"""
        suffix = self.scripts.replace("/", "_") or "root"
        out = self.cache / f"{commit}-mirror-{suffix}"
        scripts = out / self.scripts if self.scripts else out
        if out.is_dir():
            return scripts if scripts.is_dir() else None
        repository = self.repository()
        if commit not in repository:
            raise MirrorError(f"{commit} isn't in the mirror")  # never cache it as empty
        # as git archive laid it out: the scripts folder at its path in the commit
        # (no tree: the commit has no scripts folder, cached as empty)
        gitrepo.extract_atomic(repository, gitrepo.tree_at(repository, commit, self.scripts),
                               out, self.cache, prefix="mirror-", under=self.scripts)
        return scripts if scripts.is_dir() else None
