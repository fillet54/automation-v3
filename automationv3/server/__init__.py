from flask import Flask, render_template

from .requirement_views import requirements
from .workspace_views import workspace 

app = Flask(__name__)
app.register_blueprint(requirements, url_prefix='/requirements')
app.register_blueprint(workspace, url_prefix='/workspace')

@app.route('/')
def index():
    return render_template('home.html')

@app.route("/static/<path:filename>")
def serve_static(filename):
    return app.send_static_file(filename)
