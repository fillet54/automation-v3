"""The server's Flask app"""

from flask import Flask, current_app, g, has_app_context, redirect, url_for

from ..services.requirements import models as requirements
from ..services.settings import Settings
import tempfile
from pathlib import Path

from ..services.workspace import LocalWorktrees
from . import api, auth, client_mode, docs as documentation, hooks, jobs, reports, requirements as requirement_pages, scratch, ui, workspace
from .db import close_db, get_db


def requirement_lookup(id):
    """Resolve :req: references from the requirements database when
    serving: in the context the page's workspace verifies, else trunk. The
    local client asks the central server instead."""
    if not has_app_context():
        return None
    remote = current_app.config.get("REMOTE_REQUIREMENTS")
    if remote is not None:
        return remote.find(id, g.get("requirement_context"))
    return requirements.find_by_id(get_db(), id, g.get("requirement_context"))


def requirement_key():
    """What requirement_lookup answers from: the context, and the latest
    import (which may have changed any requirement's text)"""
    if not has_app_context():
        return None
    remote = current_app.config.get("REMOTE_REQUIREMENTS")
    if remote is not None:
        return remote.key(g.get("requirement_context"))
    latest = get_db().execute("SELECT MAX(id) FROM imports").fetchone()[0]
    return g.get("requirement_context") or "trunk", latest


def checked_in_cache(config):
    """Where checked-in files are extracted: CHECKED_IN_PATH, else
    checked-in/ beside the database"""
    if config.get("CHECKED_IN_PATH"):
        return Path(config["CHECKED_IN_PATH"])
    db = config.get("DB_PATH")
    if db and str(db) != ":memory:":
        return Path(db).resolve().parent / "checked-in"
    return Path(tempfile.mkdtemp(prefix="checked-in-"))


def workspace_source(config):
    """A mirror of the settings' [git] remote, else the worktrees of
    WORKSPACE_PATH, else None"""
    git = config["SETTINGS"].git if config.get("SETTINGS") else None
    if git is not None:
        from ..services.mirror import MirrorWorkspaces
        db = config.get("DB_PATH")
        base = Path(db).resolve().parent if db and str(db) != ":memory:" else Path.cwd()
        return MirrorWorkspaces(git.remote, base / git.mirror_path, checked_in_cache(config),
                                git.scripts)
    path = config.get("WORKSPACE_PATH")
    return LocalWorktrees(path, checked_in_cache(config)) if path else None


def create_app(**config):
    """The server app. Config: DB_PATH, WORKSPACE_PATH, REPORTS_PATH,
    DOCS_PATH (built HTML documentation, served at /docs) if there is one,
    SETTINGS (services.settings.Settings; default single-user), and
    WORKSPACES, a workspace source (default: the worktrees of
    WORKSPACE_PATH; see services/workspace.py).

    The local client (automation-v3 client) also gives CENTRAL, a
    services.client.CentralClient signed in to the central server, and
    LOCAL_WORKER, True when this machine runs scratch runs itself.

    CONSOLE_WORKER is the worker running in this process, if there is one
    (client --config, server --local-worker, demo): the editor's console
    borrows it (web/console.py). CONSOLE_IDLE is how long, in seconds, an
    idle console is kept open (default 30 minutes)."""
    app = Flask(__name__)
    app.config.setdefault("SETTINGS", Settings())
    app.config.update(config)
    app.config.setdefault("WORKSPACES", workspace_source(app.config))
    if app.config.get("CENTRAL") is not None:
        from ..services.client import RemoteRequirements
        app.config.setdefault("REMOTE_REQUIREMENTS", RemoteRequirements(app.config["CENTRAL"]))
    ui.init_app(app)
    auth.init_app(app)
    client_mode.init_app(app)
    # Scripts are authored in git; the workspace is a read-only viewer
    app.register_blueprint(workspace.bp, url_prefix="/workspace")
    app.register_blueprint(requirement_pages.requirements, url_prefix="/requirements")
    app.register_blueprint(jobs.jobqueue, url_prefix="/runner")
    app.register_blueprint(reports.reports, url_prefix="/reports")
    app.register_blueprint(scratch.scratch, url_prefix="/scratch")
    app.register_blueprint(hooks.hooks)
    app.register_blueprint(api.api, url_prefix="/api")
    app.teardown_appcontext(close_db)

    @app.route("/")
    def index():
        first = next(iter(app.config["WORKSPACES"].branches()), None)
        if first is None:  # e.g. a mirror of an empty remote
            return redirect(url_for("reports.index"))
        return redirect(url_for("workspace.index", id=first))

    @app.route("/plugins.css")
    def plugins_css():
        """The CSS plugins give for what their directives and blocks write"""
        from ..framework.plugins import plugin_css
        return app.response_class(plugin_css(), mimetype="text/css")

    @app.route("/docs/", defaults={"filename": "index.html"})
    @app.route("/docs/<path:filename>")
    def docs(filename):
        """The documentation, if the server was given a build of it, in the site's shell"""
        return documentation.serve(filename)

    return app
