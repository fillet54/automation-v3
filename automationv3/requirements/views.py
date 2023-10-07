from pathlib import Path
from flask import Blueprint, render_template, request, abort

from .models import Requirement

from ..server.models import db

requirements = Blueprint('requirements', __name__,
                         template_folder=Path(__file__).resolve().parent / 'templates')

@requirements.route("/", methods=["GET"])
def list():
    subsystem = request.args.get('subsystem')

    subsystems = [r.subsystem
                  for r in db.query(Requirement.subsystem).distinct()]

    query = db.query(Requirement)
    if subsystem:
        query = query.filter(Requirement.subsystem == subsystem)
    reqs = query.all()

    return render_template("requirements.html", 
                           requirements=reqs, 
                           hx_request=request.headers.get('HX-Request', False),
                           selected_subsystem=subsystem, 
                           subsystems=subsystems)


@requirements.route("/<id>", methods=["GET"])
def by_id(id):
    requirement = db.query(Requirement).filter(Requirement.id == id).one()

    if requirement is None:
        abort(404)

    return requirement.__repr_html__()


