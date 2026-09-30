import mimetypes

from flask import Flask, redirect, url_for

from .database import close_db
from .editor import commitlog, editor, workspace
from .jobqueue import jobqueue
from .requirements.views import requirements

# add support for rst mimetype
mimetypes.add_type("text/x-rst", ".rst")


app = Flask(__name__)
app.register_blueprint(workspace.bp, url_prefix="/workspace")
app.register_blueprint(editor.bp, url_prefix="/editor")
app.register_blueprint(commitlog.bp, url_prefix="/commitlog")
app.register_blueprint(requirements, url_prefix="/requirements")
app.register_blueprint(jobqueue, url_prefix="/runner")
app.teardown_appcontext(close_db)


@app.route("/")
def index():
    first = next(iter(workspace.find_worktrees(app.config["WORKSPACE_PATH"])))
    return redirect(url_for("workspace.index", id=first))
