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
from ..services.reports import runs as report_runs
from ..services import scratch as scratch_service
from ..services.reports import store
from ..services import client
from .auth import mine_only, owner_email
from .client_mode import CENTRAL, central_client, central_url, resolve_versions
from .context import checked_in_root, reports_root as root, workspace_root
from .db import get_db
from .reports import run_status

scratch = Blueprint("scratch", __name__)


def files_root(workspace, files):
    """The folder to build from: the workspace on disk, or as checked in"""
    if files == scratch_service.CHECKED_IN:
        return checked_in_root(workspace)
    return workspace_root(workspace)


def render_page(errors=(), status=200):
    runs = scratch_service.scratch_runs(root(), owner=mine_only())
    for run in runs:
        run["status"] = run_status(run)
    return render_template("scratch.html", runs=runs, errors=errors,
                           central_scratch=central_url("/scratch/") if central_client() else None), status


@scratch.route("/", methods=["GET"])
def index():
    return render_page()


@scratch.route("/run", methods=["POST"])
def run():
    """Run scripts (every variation, or the one picked) in one
    environment, or every environment each supports, from the files in
    work or as checked in. Goes to the run, or the list when there are
    several. The local client sends them to the central server's workers
    unless `where` is this machine."""
    form = request.form
    files = form.get("files") or scratch_service.IN_WORK
    workspace = form.get("workspace", "")
    source = files_root(workspace, files)
    if source is None:
        return render_page([f"There is no workspace {workspace!r} with files {files}"], 400)
    scripts, variation = form.getlist("script"), form.get("variation")
    environment = form.get("environment")
    versions = {uut: form.get(f"version-{uut}") for uut in uut_types()
                if form.get(f"version-{uut}")}
    if central_client() is not None:
        try:
            versions = resolve_versions(versions)
        except client.ClientError as e:
            return render_page([str(e)], 400)
        if form.get("where", CENTRAL) == CENTRAL:
            return run_on_central(workspace, source, scripts, environment, variation,
                                  versions)
    plan = build_plan(workspace, source, scripts, scratch=True,
                      environments=[environment] if environment else None,
                      versions=versions,
                      variations={f"{s}::{variation}" for s in scripts} if variation else None)
    try:
        run_ids = scratch_service.queue_scratch(get_db(), root(), plan, files, owner=owner_email())
    except models.QueueError as e:
        return render_page(e.errors, 400)
    if len(run_ids) == 1:
        return redirect(url_for("reports.run", report_id=scratch_service.SCRATCH, run_id=run_ids[0]))
    return redirect(url_for("scratch.index"))


def run_on_central(workspace, source, scripts, environment, variation, versions):
    """Upload the scripts' files to the central server's scratch space;
    go to the run there, or to its scratch page when there are several"""
    try:
        files = client.upload_files(source, scripts)
        runs = central_client().scratch(workspace, files, scripts, environment=environment,
                                        variation=variation, uut_versions=versions)
    except client.ClientError as e:
        return render_page(str(e).splitlines(), 400)
    if len(runs) == 1:
        return redirect(runs[0]["url"])
    return redirect(central_url("/scratch/"))


@scratch.route("/runs/<run_id>/again", methods=["POST"])
def again(run_id):
    """Run a scratch run's script again, as it is now; an uploaded one
    (whose worktree is on someone's machine) with the same files"""
    previous = store.load_run(root(), scratch_service.SCRATCH, run_id) or {}
    if previous.get("source") == scratch_service.UPLOADED:
        new_id = report_runs.rerun(get_db(), root(), scratch_service.SCRATCH, run_id, force=True,
                              owner=owner_email())
        return redirect(url_for("reports.run", report_id=scratch_service.SCRATCH, run_id=new_id))
    source = files_root(previous.get("workspace"), previous.get("source", scratch_service.IN_WORK))
    if source is None:
        return render_page(["That run's workspace is gone"], 404)
    try:
        new_id = scratch_service.run_again(get_db(), root(), source, run_id, owner=owner_email())
    except models.QueueError as e:
        return render_page(e.errors, 400)
    return redirect(url_for("reports.run", report_id=scratch_service.SCRATCH, run_id=new_id))


@scratch.route("/clear", methods=["POST"])
def clear():
    """Delete the finished scratch runs: on a central server, only yours"""
    scratch_service.clear_scratch(root(), owner=owner_email())
    return redirect(url_for("scratch.index"))
