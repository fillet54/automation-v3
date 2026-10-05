"""The server's Flask app"""

import mimetypes

from flask import Flask, has_app_context, redirect, url_for

from ..framework import rst
from ..services.requirements import models as requirements
from ..services.workspace import find_worktrees
from . import jobs, reports, requirements as requirement_pages, workspace
from .db import close_db, get_db

# add support for rst mimetype
mimetypes.add_type("text/x-rst", ".rst")


def requirement_lookup(id):
    """Resolve :req: references from the requirements table when serving"""
    if not has_app_context():
        return None
    return requirements.find_by_id(get_db(), id)


def create_app(**config):
    """The server app. Config: DB_PATH, WORKSPACE_PATH, REPORTS_PATH."""
    app = Flask(__name__)
    app.config.update(config)
    # The editor and commit log blueprints (web.editor) are parked: scripts
    # are authored in git and the workspace is a read-only viewer.
    app.register_blueprint(workspace.bp, url_prefix="/workspace")
    app.register_blueprint(requirement_pages.requirements, url_prefix="/requirements")
    app.register_blueprint(jobs.jobqueue, url_prefix="/runner")
    app.register_blueprint(reports.reports, url_prefix="/reports")
    app.teardown_appcontext(close_db)
    rst.set_requirement_lookup(requirement_lookup)

    @app.route("/")
    def index():
        first = next(iter(find_worktrees(app.config["WORKSPACE_PATH"])))
        return redirect(url_for("workspace.index", id=first))

    return app
