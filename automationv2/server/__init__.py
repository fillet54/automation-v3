from flask import Flask, render_template, g
from ..repository import RequirementsRepository

app = Flask(__name__)

def get_db():
    if 'db' not in g:
        g.db = RequirementsRepository("requirements.db")
    return g.db

@app.route('/')
def index():
    repository = get_db()
    subsystems = repository.get_subsystems()
    return render_template('index.html', subsystems=subsystems)

@app.route("/static/<path:filename>")
def serve_static(filename):
    return app.send_static_file(filename)

@app.route("/requirements/<requirement_id>", methods=["GET"])
def get_requirement_by_id(requirement_id):
    repository = get_db()
    requirement = repository.get_by_id(requirement_id)
    if requirement is None:
        return "Requirement not found", 404
    return render_template("requirement.html", requirement=requirement)

@app.route("/requirements", methods=["GET"])
def get_requirements():
    repository = get_db()
    requirements = repository.get_all()
    if requirements is None:
        return "Requirement not found", 404
    return [r.text for r in requirements]


@app.route("/subsystems", methods=["GET"])
def subsystems():
    repository = get_db()
    subsystems = sorted(repository.get_subsystems())
    return render_template("subsystems.html", subsystems=subsystems)

@app.route("/subsystems/<subsystem_id>", methods=["GET"])
def get_requirements_by_subsystem(subsystem_id):
    repository = get_db()
    requirements = repository.get_by_subsystem(subsystem_id)
    return render_template("requirements.html", requirements=requirements)

if __name__ == "__main__":
    app.run()
