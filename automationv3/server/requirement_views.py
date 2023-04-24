
from flask import Blueprint, render_template, request

from .models import get_db

requirements = Blueprint('requirements', __name__,
                        template_folder='templates')
@requirements.route("/", methods=["GET"])
def list():
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

@requirements.route("/<requirement_id>", methods=["GET"])
def by_id(requirement_id):
    repository = get_db()
    requirement = repository.get_by_id(requirement_id)
    if requirement is None:
        return "Requirement not found", 404
    return render_template("partials/requirement.html", requirement=requirement)

