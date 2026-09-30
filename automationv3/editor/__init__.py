from flask import Flask, redirect, url_for
import mimetypes

from ..database import close_db
from ..jobqueue import jobqueue
from ..requirements.views import requirements
from .views import editor, workspace, commitlog
from .workspace import find_worktrees


# add support for rst mimetype
mimetypes.add_type("text/x-rst", ".rst")


app = Flask(__name__)
app.register_blueprint(requirements, url_prefix="/requirements")
app.register_blueprint(workspace, url_prefix="/workspace")
app.register_blueprint(editor, url_prefix="/editor")
app.register_blueprint(jobqueue, url_prefix="/runner")
app.register_blueprint(commitlog, url_prefix="/commitlog")


@app.route("/")
def index():
    first = next(iter(find_worktrees(app.config["WORKSPACE_PATH"])))
    return redirect(url_for("workspace.index", id=first))


@app.route("/static/<path:filename>")
def serve_static(filename):
    return app.send_static_file(filename)


app.teardown_appcontext(close_db)
