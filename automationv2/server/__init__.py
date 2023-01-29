from flask import Flask, render_template, g
from ..repository import RequirementsRepository

app = Flask(__name__)

def get_db():
    if 'db' not in g:
        g.db = RequirementsRepository("requirements.db")
    return g.db

@app.route("/requirements/<requirement_id>", methods=["GET"])
def get_requirement_by_id(requirement_id):
    repository = get_db()
    print("ID", f"'{requirement_id}'")
    requirement = repository.get(requirement_id)
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
    #return render_template("requirement.html", requirement=requirement)
if __name__ == "__main__":
    app.run()
