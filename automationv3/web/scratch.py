"""The scratch space: run scripts under development, outside any report"""

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)

from ..framework.planning import build_plan
from ..framework.uut import uut_types
from ..services import jobs as models
from ..services.reports import store
from ..services.requirements import links
from ..services.workspace import find_worktrees
from .db import get_db
from .jobs import live_environments
from .reports import run_status, uut_choices

scratch = Blueprint("scratch", __name__)


def root():
    return current_app.config["REPORTS_PATH"]


def worktrees():
    return find_worktrees(current_app.config["WORKSPACE_PATH"])


def render_page(form, errors=()):
    roots = worktrees()
    workspace = form.get("workspace") or next(iter(roots), None)
    runs = models.scratch_runs(root())
    for run in runs:
        run["status"] = run_status(run)
    return render_template(
        "scratch.html",
        workspaces=sorted(roots),
        workspace=workspace,
        scripts=links.scripts(roots[workspace]) if workspace in roots else [],
        environments=sorted(live_environments()),
        choices=uut_choices(),
        form=form,
        runs=runs,
        errors=errors,
    )


@scratch.route("/", methods=["GET"])
def index():
    return render_page(request.args)


@scratch.route("/run", methods=["POST"])
def run():
    """Run the picked scripts, every variation, in one environment (or
    every environment each supports)"""
    form = request.form
    workspace_root = worktrees().get(form.get("workspace"))
    if workspace_root is None:
        return render_page(form, ["Pick a workspace"]), 400
    environment = form.get("environment")
    versions = {uut: form.get(f"version-{uut}") for uut in uut_types()
                if form.get(f"version-{uut}")}
    plan = build_plan(form["workspace"], workspace_root, form.getlist("script"),
                      environments=[environment] if environment else None,
                      versions=versions)
    try:
        models.queue_scratch(get_db(), root(), plan)
    except models.QueueError as e:
        return render_page(form, e.errors), 400
    return redirect(url_for("scratch.index", workspace=form["workspace"]))


@scratch.route("/runs/<run_id>/again", methods=["POST"])
def again(run_id):
    """Run a scratch run's script again, as it is now"""
    previous = store.load_run(root(), models.SCRATCH, run_id)
    workspace_root = worktrees().get((previous or {}).get("workspace"))
    if workspace_root is None:
        return render_page(request.form, ["That run's workspace is gone"]), 404
    try:
        new_id = models.run_again(get_db(), root(), workspace_root, run_id)
    except models.QueueError as e:
        return render_page(request.form, e.errors), 400
    return redirect(url_for("reports.run", report_id=models.SCRATCH, run_id=new_id))


@scratch.route("/clear", methods=["POST"])
def clear():
    """Delete the finished scratch runs"""
    models.clear_scratch(root())
    return redirect(url_for("scratch.index", workspace=request.form.get("workspace")))
