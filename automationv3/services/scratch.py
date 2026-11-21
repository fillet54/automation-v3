"""Scratch run lifecycle: runs of scripts under development.

Scratch runs live in the reserved `scratch` folder of the reports root,
which has no report.json, so they never appear in a report or a rollup.
They run the workspace's files as they are on disk ("in work"),
uncommitted changes included, or as checked in, and can be cleared.
"""

from ..framework.planning import build_plan
from .reports import store

SCRATCH = "scratch"
IN_WORK, CHECKED_IN, UPLOADED = "in work", "checked in", "uploaded"


def queue_scratch(conn, root, plan, files=IN_WORK, owner=None, **run_fields):
    """Queue every run of `plan` in the scratch space. `files` says which
    of the workspace's files the plan was built from: IN_WORK (on disk),
    CHECKED_IN or UPLOADED (from a client's worktree). `owner` is who
    runs them. Returns the run ids."""
    from . import jobs

    jobs.check_runnable(plan)
    return jobs.enqueue_plan(
        conn, root, SCRATCH, plan, owner=owner,
        workspace=plan.workspace, source=files, **run_fields,
    )


def scratch_runs(root, owner=None):
    """Scratch runs, newest first; only `owner`'s, if given"""
    runs = reversed(store.list_runs(root, SCRATCH))
    return [r for r in runs if owner is None or r.get("queued_by") == owner]


def run_again(conn, root, workspace_root, run_id, owner=None):
    """Queue a scratch run again with the script as it is now: the same
    script, environment, variation and UUT versions, from `workspace_root`
    (the run's files: in work or checked in). Returns the run id."""
    run = store.load_run(root, SCRATCH, run_id)
    variation = (run.get("variation") or {}).get("name")
    plan = build_plan(
        run.get("workspace", ""),
        workspace_root,
        [run["script"]],
        scratch=True,
        environments=[run["environment"]] if run.get("environment") else None,
        versions={uut: v["id"] for uut, v in (run.get("uut_versions") or {}).items()},
        variations={f"{run['script']}::{variation}"} if variation else None,
    )
    (run_id,) = queue_scratch(conn, root, plan, run.get("source", IN_WORK), owner=owner)
    return run_id


def clear_scratch(root, owner=None):
    """Delete the finished scratch runs (only `owner`'s, if given); queued
    and running ones stay. Returns how many were deleted."""
    finished = [run for run in scratch_runs(root, owner) if run.get("outcome")]
    for run in finished:
        store.delete_run(root, SCRATCH, run["id"])
    return len(finished)
