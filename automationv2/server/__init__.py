from flask import Flask, render_template, request, g
from ..repository import RequirementsRepository

from .requirement_views import requirements

app = Flask(__name__)
app.register_blueprint(requirements, url_prefix='/requirements')

def get_db():
    if 'db' not in g:
        g.db = RequirementsRepository(app.config['DB_PATH'])
    return g.db

@app.route('/')
def index():
    repository = get_db()
    subsystems = repository.get_subsystems()
    return render_template('requirements.html', subsystems=subsystems)

@app.route("/static/<path:filename>")
def serve_static(filename):
    return app.send_static_file(filename)
