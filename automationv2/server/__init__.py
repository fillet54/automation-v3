from flask import Flask, render_template

from .models import get_db
from .requirement_views import requirements

app = Flask(__name__)
app.register_blueprint(requirements, url_prefix='/requirements')

@app.route('/')
def index():
    subsystems = get_db().get_subsystems()
    return render_template('requirements.html', subsystems=subsystems)

@app.route("/static/<path:filename>")
def serve_static(filename):
    return app.send_static_file(filename)
