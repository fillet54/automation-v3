"""A central server's workspaces: a mirror of the team's git remote

The server keeps a bare `git clone --mirror` of the remote and shows every
branch at its tip. Nothing is edited on the server, so every file is
checked in: a branch's files are its tip's rvts folder, extracted once per
commit under the cache. The mirror is fetched when the git host's webhook
says something was pushed, and again before a report is queued, so a
report never runs a stale commit (see web/hooks.py and web/jobs.py).

Same interface as services.workspace.LocalWorktrees.
"""

import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import threading
from pathlib import Path, PurePosixPath

RVTS = "rvts"


class MirrorError(RuntimeError):
    pass


class MirrorWorkspaces:
    editable = False  # what the server shows is what was pushed

    def __init__(self, remote, path, cache):
        self.remote = remote
        self.path = Path(path)
        self.cache = Path(cache)
        self.lock = threading.Lock()

    def git(self, *args, binary=False, check=True):
        result = subprocess.run(["git", *args], cwd=self.path, capture_output=True,
                                timeout=300)
        if check and result.returncode != 0:
            raise MirrorError(f"git {' '.join(args)}: "
                              f"{result.stderr.decode(errors='replace').strip()}")
        return result.stdout if binary else result.stdout.decode()

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
        """branch -> its rvts folder at its tip (branches without one are left out)"""
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
            return self.git("show", f"{commit}:{RVTS}/{PurePosixPath(path)}")
        except MirrorError:
            return None

    def extract(self, commit):
        """The rvts folder of `commit`, extracted once under the cache; None
        if the commit has none"""
        out = self.cache / f"{commit}-mirror"
        if out.is_dir():
            return out / RVTS if (out / RVTS).is_dir() else None
        try:
            archive = self.git("archive", "--format=tar", commit, RVTS, binary=True)
        except MirrorError:  # no rvts folder in that commit
            archive = None
        self.cache.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="mirror-", dir=self.cache))
        try:
            if archive:
                with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                    tar.extractall(work, filter="data")
            try:
                os.replace(work, out)
            except OSError:
                if not out.is_dir():  # not another request writing it first
                    raise
        finally:
            shutil.rmtree(work, ignore_errors=True)
        return out / RVTS if (out / RVTS).is_dir() else None
