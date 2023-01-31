from flask import Flask, render_template, request, g
from ..repository import RequirementsRepository

app = Flask(__name__)

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

@app.route("/requirements/<requirement_id>", methods=["GET"])
def get_requirement_by_id(requirement_id):
    repository = get_db()
    requirement = repository.get_by_id(requirement_id)
    if requirement is None:
        return "Requirement not found", 404
    return render_template("partials/requirement.html", requirement=requirement)

@app.route("/requirements", methods=["GET"])
def get_requirements():
    repository = get_db()
    hx_request = request.headers.get('HX-Request', False)
    subsystem = request.args.get('subsystem')
    subsystems = sorted(repository.get_subsystems())
    requirements = repository.get_by_subsystem(subsystem) if subsystem else repository.get_all()
    return render_template("requirements.html", 
                           requirements=requirements, 
                           hx_request=hx_request, 
                           selected_subsystem=subsystem, 
                           subsystems=subsystems)


@app.route("/subsystems", methods=["GET"])
def subsystems():
    repository = get_db()
    subsystems = sorted(repository.get_subsystems())
    return render_template("partials/subsystems.html", subsystems=subsystems)

if __name__ == "__main__":
    app.config['DB_PATH'] = 'requirements.db'
    app.run()
