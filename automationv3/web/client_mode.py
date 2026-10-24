"""The local client's web UI: the same pages, on this machine's worktrees

`automation-v3 client` serves the workspace pages on your own git
worktrees, so scripts are checked as you write them. What belongs to the
team lives on the central server (CENTRAL in the app's config): the
header's Requirements, Queue, Reports and Workers go there, :req:
references are looked up there, and Run in scratch sends the files there
to run on its workers, unless you pick this machine (LOCAL_WORKER), whose
results stay here. Queue opens the central server's dialog for the
branch, which runs what was pushed.
"""

import time
from urllib.parse import urlencode

from flask import current_app

from ..services.client import ClientError

# How long the central server's live environments are kept
ENVIRONMENTS_TTL = 15

CENTRAL_NAV = {"requirements": "/requirements/", "queue": "/runner/",
               "reports": "/reports/", "workers": "/runner/workers"}

HERE, CENTRAL = "local", "central"


def central():
    """The CentralClient, when this app is the local client"""
    return current_app.config.get("CENTRAL")


def central_url(path, **params):
    query = urlencode([(k, v) for k, v in params.items() if v not in (None, "")],
                      doseq=True)
    return central().server + path + (f"?{query}" if query else "")


def local_worker():
    return bool(current_app.config.get("LOCAL_WORKER"))


def central_environments():
    """environment -> live worker urls on the central server ({} if it
    can't be reached), kept for a few seconds"""
    cached = current_app.config.get("_CENTRAL_ENVIRONMENTS")
    if cached and time.monotonic() - cached[0] < ENVIRONMENTS_TTL:
        return cached[1]
    try:
        found = central().environments()
    except ClientError:
        found = {}
    current_app.config["_CENTRAL_ENVIRONMENTS"] = (time.monotonic(), found)
    return found


def init_app(app):
    @app.context_processor
    def client_context():
        if app.config.get("CENTRAL") is None:
            return {"client_mode": False}
        return {"client_mode": True, "central_server": app.config["CENTRAL"].server,
                "local_worker": local_worker(), "central_url": central_url}
