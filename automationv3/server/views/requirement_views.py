from pathlib import Path
from flask import Blueprint, render_template, request

from ..templates import template_root
from ..models import get_requirements

requirements = Blueprint('requirements', __name__,
                         template_folder=template_root)

@requirements.route("/", methods=["GET"])
def list():
    subsystem = request.args.get('subsystem')
    subsystems = get_requirements().get_subsystems()
    requirements = get_requirements().get_by_subsystem(subsystem) if subsystem else get_requirements().get_all()
    return render_template("requirements.html", 
                           requirements=requirements, 
                           hx_request=request.headers.get('HX-Request', False),
                           selected_subsystem=subsystem, 
                           subsystems=subsystems)


@requirements.route("/<requirement_id>", methods=["GET"])
def by_id(requirement_id):
    requirement = get_requirements().get_by_id(requirement_id)
    if requirement is None:
        return "Requirement not found", 404
    return render_template("partials/requirement.html", requirement=requirement)

