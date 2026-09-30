from pathlib import Path
from flask import Blueprint, render_template, request, abort

from . import models
from ..database import get_db

requirements = Blueprint(
    "requirements",
    __name__,
    template_folder=Path(__file__).resolve().parent / "templates",
)


@requirements.route("/", methods=["GET"])
def list():
    subsystem = request.args.get("subsystem")

    conn = get_db()
    subsystems = models.subsystems(conn)
    reqs = models.find_all(conn, subsystem)

    return render_template(
        "requirements.html",
        requirements=reqs,
        hx_request=request.headers.get("HX-Request", False),
        selected_subsystem=subsystem,
        subsystems=subsystems,
    )


@requirements.route("/<id>", methods=["GET"])
def by_id(id):
    requirement = models.find_by_id(get_db(), id)

    if requirement is None:
        abort(404)

    return requirement.__repr_html__()
