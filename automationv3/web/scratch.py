"""The scratch space: run scripts under development, outside any report

Runs start from a script's page in the workspace (Run in scratch), with
the files in work (on disk) or as checked in; this page lists them, to
open, run again or clear.
"""

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
from .db import get_db
from .jobs import checked_in_root, workspace_root
from .reports import run_status

scratch = Blueprint("scratch", __name__)


def root():
    return current_app.config["REPORTS_PATH"]


def files_root(workspace, files):
    """The folder to build from: the workspace on disk, or as checked in"""
    if files == models.CHECKED_IN:
        return checked_in_root(workspace)
    return workspace_root(workspace)


def render_page(errors=(), status=200):
    runs = models.scratch_runs(root())
    for run in runs:
        run["status"] = run_status(run)
    return render_template("scratch.html", runs=runs, errors=errors), status


@scratch.route("/", methods=["GET"])
def index():
    return render_page()


@scratch.route("/run", methods=["POST"])
def run():
    """Run scripts (every variation, or the one picked) in one
    environment, or every environment each supports, from the files in
    work or as checked in. Goes to the run, or the list when there are
    several."""
    form = request.form
    files = form.get("files") or models.IN_WORK
    workspace = form.get("workspace", "")
    source = files_root(workspace, files)
    if source is None:
        return render_page([f"There is no workspace {workspace!r} with files {files}"], 400)
    scripts, variation = form.getlist("script"), form.get("variation")
    environment = form.get("environment")
    versions = {uut: form.get(f"version-{uut}") for uut in uut_types()
                if form.get(f"version-{uut}")}
    plan = build_plan(workspace, source, scripts,
                      environments=[environment] if environment else None,
                      versions=versions,
                      variations={f"{s}::{variation}" for s in scripts} if variation else None)
    try:
        run_ids = models.queue_scratch(get_db(), root(), plan, files)
    except models.QueueError as e:
        return render_page(e.errors, 400)
    if len(run_ids) == 1:
        return redirect(url_for("reports.run", report_id=models.SCRATCH, run_id=run_ids[0]))
    return redirect(url_for("scratch.index"))


@scratch.route("/runs/<run_id>/again", methods=["POST"])
def again(run_id):
    """Run a scratch run's script again, as it is now"""
    previous = store.load_run(root(), models.SCRATCH, run_id) or {}
    source = files_root(previous.get("workspace"), previous.get("source", models.IN_WORK))
    if source is None:
        return render_page(["That run's workspace is gone"], 404)
    try:
        new_id = models.run_again(get_db(), root(), source, run_id)
    except models.QueueError as e:
        return render_page(e.errors, 400)
    return redirect(url_for("reports.run", report_id=models.SCRATCH, run_id=new_id))


@scratch.route("/clear", methods=["POST"])
def clear():
    """Delete the finished scratch runs"""
    models.clear_scratch(root())
    return redirect(url_for("scratch.index"))
