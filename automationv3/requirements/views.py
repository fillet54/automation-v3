from pathlib import Path
from flask import Blueprint, render_template, request, abort

from .models import Requirement
from ..database import db

requirements = Blueprint('requirements', __name__,
                         template_folder=Path(__file__).resolve().parent / 'templates')

@requirements.route("/", methods=["GET"])
def list():
    subsystem = request.args.get('subsystem')

    with db.session as session:
        subsystems = [r.subsystem
                      for r in session.query(Requirement.subsystem).distinct()]

        query = session.query(Requirement)
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
    with db.session as session:
        requirement = Requirement.find_by_id(session, id)

    if requirement is None:
        abort(404)

    return requirement.__repr_html__()


