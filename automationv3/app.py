import mimetypes

from flask import Flask, redirect, url_for

from .database import close_db
from .editor import workspace
from .jobqueue import jobqueue
from .reports.views import reports
from .requirements.views import requirements

# add support for rst mimetype
mimetypes.add_type("text/x-rst", ".rst")


app = Flask(__name__)
# The editor and commit log blueprints are parked: scripts are authored in
# git and the workspace is a read-only viewer.
app.register_blueprint(workspace.bp, url_prefix="/workspace")
app.register_blueprint(requirements, url_prefix="/requirements")
app.register_blueprint(jobqueue, url_prefix="/runner")
app.register_blueprint(reports, url_prefix="/reports")
app.teardown_appcontext(close_db)


@app.route("/")
def index():
    first = next(iter(workspace.find_worktrees(app.config["WORKSPACE_PATH"])))
    return redirect(url_for("workspace.index", id=first))
