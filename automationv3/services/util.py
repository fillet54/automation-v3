"""Shared service primitives: UTC timestamps, atomic writes, and git helpers."""

import functools
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from .. import __version__

PACKAGE = Path(__file__).resolve().parents[1]


# UTC timestamps


def utcnow():
    """Current UTC time, timezone-aware, to the second."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def utcnow_naive():
    """Current UTC time without tzinfo, for SQLite CURRENT_TIMESTAMP comparisons."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(when=None, timespec="seconds"):
    """Format `when` (default: now) as a UTC ISO-8601 string."""
    when = datetime.now(timezone.utc) if when is None else when.astimezone(timezone.utc)
    return when.isoformat(timespec=timespec)


def now_iso():
    """Current UTC time as an ISO-8601 string to the second."""
    return iso(timespec="seconds")


# Atomic writes


def replace(source, target, attempts=20):
    """os.replace, retried briefly on Windows: there it fails while
    another thread or process has `target` open (a page reading a
    run.json as the worker rewrites it); elsewhere it never does"""
    for attempt in range(attempts):
        try:
            return os.replace(source, target)
        except PermissionError:
            if os.name != "nt" or attempt == attempts - 1:
                raise
            time.sleep(0.05)


def atomic_write(path, content, mode=None):
    """Replace `path` with `content` (str or bytes) atomically via mkstemp."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8") if isinstance(content, str) else content
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        if mode is not None:
            os.chmod(tmp, mode)
        elif path.exists():
            os.chmod(tmp, path.stat().st_mode & 0o777)
        else:
            os.chmod(tmp, 0o644)
        replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json(path, data, mode=None):
    """Serialize `data` as pretty JSON and write it atomically."""
    atomic_write(path, json.dumps(data, indent=2), mode=mode)


# Git (the mirror's clone and fetch; everything else reads through services/repo.py)


def git(cwd, *args, binary=False, timeout=None):
    """Run git in `cwd` and return stdout (bytes if `binary`, else UTF-8 str)."""
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, timeout=timeout, check=True
    )
    return result.stdout if binary else result.stdout.decode("utf-8")


@functools.lru_cache(maxsize=1)
def framework_fingerprint():
    """The framework's version; for a git checkout, its commit and
    whether it has uncommitted changes (a dev install)"""
    from . import repo
    try:
        found = repo.open_repo(PACKAGE)
        head = repo.head_commit(found)
    except repo.GitError:
        head = None
    if head is None:
        return {"version": __version__, "git": None, "dev": False}
    try:
        dirty = repo.is_dirty(found)
    except Exception:
        dirty = False
    return {"version": __version__, "git": head, "dev": dirty}
