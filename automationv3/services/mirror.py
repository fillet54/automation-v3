"""A central server's workspaces: a mirror of the team's git remote

The server keeps a bare `git clone --mirror` of the remote and shows every
branch at its tip. Nothing is edited on the server, so every file is
checked in: a branch's files are its tip's scripts folder (`scripts`, a
path in the repository; "" for its top), extracted once per commit under
the cache. The mirror is fetched when the git host's webhook
says something was pushed, and again before a report is queued, so a
report never runs a stale commit (see web/hooks.py and web/jobs.py).

Same interface as services.workspace.LocalWorktrees.
"""

import shutil
import subprocess
import threading
from pathlib import Path, PurePosixPath

from .util import extract_tar_atomic, git as run_git

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

    def commits(self):
        """branch -> the commit at its tip"""
        if not (self.path / "HEAD").exists():
            return {}
        out = self.git("for-each-ref", "--format=%(refname:short) %(objectname)",
                       "refs/heads")
        return dict(line.split(" ", 1) for line in out.splitlines() if line)

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
        try:
            return self.git("show", f"{commit}:{PurePosixPath(self.scripts, path)}")
        except MirrorError:
            return None

    def extract(self, commit):
        """The scripts folder of `commit`, extracted once under the cache;
        None if the commit has none"""
        suffix = self.scripts.replace("/", "_") or "root"
        out = self.cache / f"{commit}-mirror-{suffix}"
        scripts = out / self.scripts if self.scripts else out
        if out.is_dir():
            return scripts if scripts.is_dir() else None
        try:
            archive = self.git("archive", "--format=tar", commit,
                               *([self.scripts] if self.scripts else []), binary=True)
        except MirrorTimeout:
            raise  # says nothing about the commit: never cache it as empty
        except MirrorError:  # no scripts folder in that commit
            archive = None
        extract_tar_atomic(archive, out, self.cache, prefix="mirror-")
        return scripts if scripts.is_dir() else None
