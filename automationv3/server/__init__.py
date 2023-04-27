from flask import Flask, render_template

from .views.requirement_views import requirements
from .views.workspace_views import workspace, index as workspace_index 

app = Flask(__name__)
app.register_blueprint(requirements, url_prefix='/requirements')
app.register_blueprint(workspace, url_prefix='/workspace')

@app.route('/')
def index():
    return workspace_index(id=0,)

@app.route("/static/<path:filename>")
def serve_static(filename):
    return app.send_static_file(filename)
