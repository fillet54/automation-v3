"""Shared web request/app helpers: workspaces, reports root, live environments,
and cache directories beside DB_PATH."""

import tempfile
from pathlib import Path

from flask import current_app

from ..services import jobs as models
from .client_mode import central_client, central_environments
from .db import get_db


def cache_dir(config, key, folder, prefix=None):
    """A cache directory from `config[key]`, else `folder` if absolute,
    else `<folder>` beside DB_PATH, else a temporary directory (memoized
    in `config[key]`)."""
    if not config.get(key):
        db = config.get("DB_PATH")
        config[key] = (
            Path(folder) if Path(folder).is_absolute()
            else Path(db).resolve().parent / folder
            if db and str(db) != ":memory:"
            else Path(tempfile.mkdtemp(prefix=prefix or f"{folder}-"))
        )
    return Path(config[key])


def reports_root():
    return current_app.config["REPORTS_PATH"]


def workspaces():
    """The app's workspace source (services/workspace.py): WORKSPACES, else
    the worktrees of WORKSPACE_PATH"""
    config = current_app.config
    if config.get("WORKSPACES") is None:
        from .app import workspace_source
        config["WORKSPACES"] = workspace_source(config)
    return config["WORKSPACES"]


def workspace_root(name):
    """The scripts folder of branch `name` as the workspace shows it, or None"""
    return workspaces().root(name) if name else None


def checked_in_root(name):
    """The scripts folder of branch `name` as checked in, which reports run; None
    for an unknown branch or one with nothing committed"""
    return workspaces().checked_in(name) if name else None


def live_environments():
    """environment -> live worker urls: this server's, and in client mode
    the central server's too"""
    since = models.utcnow() - models.MISSING_AFTER
    found = {}
    for worker in models.find_workers(get_db(), since=since):
        for env in worker.environments:
            found.setdefault(env, []).append(worker.url)
    if central_client() is not None:
        for env, urls in central_environments().items():
            found.setdefault(env, []).extend(urls)
    return found
