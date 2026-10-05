"""Requirements pages"""

from flask import Blueprint, current_app, render_template, request, abort

from ..services.requirements import links, models
from ..services.workspace import find_worktrees
from .db import get_db

requirements = Blueprint("requirements", __name__)


def workspaces():
    """branch -> rvts root, or {} when no workspace is configured"""
    path = current_app.config.get("WORKSPACE_PATH")
    return find_worktrees(path) if path else {}


@requirements.route("/", methods=["GET"])
def list():
    subsystem = request.args.get("subsystem")

    conn = get_db()
    subsystems = models.subsystems(conn)
    reqs = models.find_all(conn, subsystem)

    # Scripts referencing each requirement in the chosen workspace
    roots = workspaces()
    workspace = request.args.get("workspace") or next(iter(roots), None)
    linked = {}
    if workspace in roots:
        links.refresh(conn, workspace, roots[workspace])
        linked = links.scripts_by_requirement(conn, workspace)
        if not subsystem:
            known = {r.id for r in reqs}
            reqs += [models.Requirement(id) for id in sorted(linked) if id not in known]

    return render_template(
        "requirements.html",
        requirements=reqs,
        linked=linked,
        workspace=workspace,
        workspaces=sorted(roots),
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
