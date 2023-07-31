from pathlib import Path
from flask import Blueprint, render_template, request, abort

from automationv3.models import Requirement

from ..templates import template_root
from ..models import db

requirements = Blueprint('requirements', __name__,
                         template_folder=template_root)

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

    return render_template("partials/requirement.html",
                           requirement=requirement)


