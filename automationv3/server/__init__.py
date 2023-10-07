from flask import Flask, render_template, g, redirect, url_for

from ..runner import runner
from ..requirements.views import requirements
from .views import editor, workspace
from .models import get_workspaces

app = Flask(__name__)
app.register_blueprint(requirements, url_prefix='/requirements')
app.register_blueprint(workspace, url_prefix='/workspace')
app.register_blueprint(editor, url_prefix='/editor')
app.register_blueprint(runner, url_prefix='/runner')

@app.route('/')
def index():
    workspaces = get_workspaces()
    workspace = workspaces[0]

    return redirect(url_for('workspace.index', path=workspace.id))


@app.route("/static/<path:filename>")
def serve_static(filename):
    return app.send_static_file(filename)


# cleanup database connection
@app.teardown_appcontext
def close_db(error):
    """Closes the database again at the end of the request."""
    if hasattr(g, 'sqlite_db'):
        g.sqlite_db.close()

    if hasattr(g, 'session'):
        g.session.close()
