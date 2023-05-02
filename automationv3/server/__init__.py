from flask import Flask, render_template, g

from .views.requirement_views import requirements
from .views.workspace_views import workspace, index as workspace_index 
from .views.editor_views import editor

app = Flask(__name__)
app.register_blueprint(requirements, url_prefix='/requirements')
app.register_blueprint(workspace, url_prefix='/workspace')
app.register_blueprint(editor, url_prefix='/editor')

@app.route('/')
def index():
    return workspace_index(id=0,)

@app.route("/static/<path:filename>")
def serve_static(filename):
    return app.send_static_file(filename)


# cleanup database connection
@app.teardown_appcontext
def close_db(error):
    """Closes the database again at the end of the request."""
    if hasattr(g, 'sqlite_db'):
        g.sqlite_db.close()
