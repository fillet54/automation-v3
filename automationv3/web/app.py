"""The server's Flask app"""

from flask import Flask, g, has_app_context, redirect, url_for

from ..framework import rst
from ..services.requirements import models as requirements
from ..services.settings import Settings
import tempfile
from pathlib import Path

from ..services.workspace import LocalWorktrees
from . import auth, docs as documentation, jobs, reports, requirements as requirement_pages, scratch, ui, workspace
from .db import close_db, get_db


def requirement_lookup(id):
    """Resolve :req: references from the requirements database when
    serving: in the context the page's workspace verifies, else trunk"""
    if not has_app_context():
        return None
    return requirements.find_by_id(get_db(), id, g.get("requirement_context"))


def requirement_key():
    """What requirement_lookup answers from: the context, and the latest
    import (which may have changed any requirement's text)"""
    if not has_app_context():
        return None
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
    """The worktrees of WORKSPACE_PATH, or None without one"""
    path = config.get("WORKSPACE_PATH")
    return LocalWorktrees(path, checked_in_cache(config)) if path else None


def create_app(**config):
    """The server app. Config: DB_PATH, WORKSPACE_PATH, REPORTS_PATH,
    DOCS_PATH (built HTML documentation, served at /docs) if there is one,
    SETTINGS (services.settings.Settings; default single-user), and
    WORKSPACES, a workspace source (default: the worktrees of
    WORKSPACE_PATH; see services/workspace.py)."""
    app = Flask(__name__)
    app.config.setdefault("SETTINGS", Settings())
    app.config.update(config)
    app.config.setdefault("WORKSPACES", workspace_source(app.config))
    ui.init_app(app)
    auth.init_app(app)
    # Scripts are authored in git; the workspace is a read-only viewer
    app.register_blueprint(workspace.bp, url_prefix="/workspace")
    app.register_blueprint(requirement_pages.requirements, url_prefix="/requirements")
    app.register_blueprint(jobs.jobqueue, url_prefix="/runner")
    app.register_blueprint(reports.reports, url_prefix="/reports")
    app.register_blueprint(scratch.scratch, url_prefix="/scratch")
    app.teardown_appcontext(close_db)
    rst.set_requirement_lookup(requirement_lookup, requirement_key)

    @app.route("/")
    def index():
        first = next(iter(app.config["WORKSPACES"].branches()))
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
