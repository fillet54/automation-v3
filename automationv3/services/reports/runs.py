"""Report creation, plan additions, and reruns."""

from ...framework.closure import resolve
from ...framework.planning import build_plan
from ..util import now_iso
from . import export, rollup, store
from ..requirements import models as requirement_models


def known_requirements(conn, ids, context=None):
    """The requirements of `ids` in `context` (trunk by default)"""
    found = (requirement_models.find_by_id(conn, id, context) for id in ids)
    return [r for r in found if r is not None]


def pinned_context(conn, context=None):
    """`context` as one fixed version: trunk becomes trunk@N, the import
    it is as of now; baselines and sets never change"""
    context = context or "trunk"
    if context != "trunk":
        return context
    latest = requirement_models.latest_import_id(conn)
    return f"trunk@{latest}" if latest else context


def requirement_snapshots(conn, ids, context=None):
    """id -> what a report keeps of each requirement it tests: {"spec",
    "context" (pinned: where links open the text as tested), "text",
    "text_hash", "subsystem"}, for the requirements the database knows"""
    pinned = pinned_context(conn, context)
    return {r.id: {"spec": r.spec, "context": pinned, "text": r.text,
                   "text_hash": r.text_hash, "subsystem": r.subsystem}
            for r in known_requirements(conn, ids, context)}


def requirement_versions(conn, ids, context=None):
    """id -> {"spec", "version", "text_hash"} of the requirements the
    database knows: the versions a report or run verifies"""
    return {r.id: {"spec": r.spec, "version": r.version, "text_hash": r.text_hash}
            for r in known_requirements(conn, ids, context) if r.version}


def create_report(root, workspace, name="", uut_versions=None, template=None,
                  owner=None):
    """An empty report for one workspace. Its UUT versions (name ->
    {id, digest}) are the default for every addition. It keeps a copy of
    `template` (the workspace's report template; default the built-in
    one) and starts its document from the template's report.rst. `owner`
    (an email; None on a single-user server) may change it, with the
    collaborators they add."""
    people = {"owner": owner, "collaborators": []} if owner else {}
    report_id = store.create_report(root, name=name, workspace=workspace,
                                    uut_versions=uut_versions or {}, requirements={},
                                    scripts=[], additions=[], **people)
    export.install_template(root, report_id, template)
    return report_id


def merge_scripts(entries, added):
    """A report's script entries with an addition's merged in: a script
    added again keeps every combination it was expected to cover"""
    merged = {entry["script"]: entry for entry in entries if isinstance(entry, dict)}
    for entry in added:
        before = merged.get(entry["script"], {})
        expected = list(before.get("expected", []))
        expected += [combo for combo in entry["expected"] if combo not in expected]
        requirements = sorted({*before.get("requirements", []), *entry["requirements"]})
        merged[entry["script"]] = {**entry, "expected": expected,
                                   "requirements": requirements}
    return list(merged.values())


def add_plan(conn, root, report_id, plan, requirements=None, context=None, owner=None,
             commit=None):
    """Queue every run of `plan` in an existing report. `requirements`
    (id -> linked scripts) join the report's tracked requirements.

    Returns the run ids. Raises QueueError if nothing can run and there
    are no requirements to track: requirements without tests yet are
    tracked all the same.
    """
    from .. import jobs

    jobs.check_runnable(plan, track=bool(requirements))
    jobs.check_open(root, report_id)
    runs = plan.runs()
    report = store.load_report(root, report_id)
    context = report.get("requirement_context") or context or "trunk"
    current = report.get("uut_versions") or {}
    plan.uut_versions = {name: current.get(name, version)
                         for name, version in plan.uut_versions.items()}
    versions = {**current, **{name: version for name, version in plan.uut_versions.items()
                              if name not in current and runs}}
    summary = plan.summary()
    store.update_report(
        root,
        report_id,
        uut_versions=versions,
        requirements={**report.get("requirements", {}), **(requirements or {})},
        requirement_context=context,
        requirement_snapshots={
            **requirement_snapshots(conn, [r for r in requirements or {}
                                           if r not in report.get("requirement_snapshots", {})],
                                    context),
            **report.get("requirement_snapshots", {})},
        scripts=merge_scripts(report.get("scripts", []), summary["scripts"]),
        additions=[*report.get("additions", []), {
            "added": now_iso(),
            "requirements": sorted(requirements or {}),
            "scripts": [s.script for s in plan.scripts],
            "environments": plan.environments,
            "uut_versions": plan.uut_versions,
            "filter": plan.filter,
            "runs": len(runs),
            **({"by": owner} if owner else {}),
            **({"commit": commit} if commit else {}),
        }],
    )

    extra = {"commit": commit} if commit else {}
    return jobs.enqueue_plan(
        conn, root, report_id, plan, owner=owner,
        extra_for=lambda sp: {
            "requirement_versions": {
                id: v["text_hash"] for id, v in
                requirement_versions(conn, sp.requirements, context).items()},
            **extra,
        },
    )


def default_name(plan):
    """What a report queued in one step covers, e.g. "R1, R2 and 3 more" """
    names = list(plan.requirements) or [s.script.split("/")[-1] for s in plan.scripts]
    if len(names) > 3:
        return f"{', '.join(names[:2])} and {len(names) - 2} more"
    return ", ".join(names)


def queue_plan(conn, root, plan, name=None, context=None, template=None, owner=None,
               commit=None):
    """Queue every run of `plan` under one new report, tracking the
    requirements it covers: the one-step path from a selection. `owner`
    owns the new report.

    Returns (report_id, run_ids). Raises QueueError if the plan has
    errors, or nothing to run and no requirements to track.
    """
    from .. import jobs

    jobs.check_runnable(plan, track=True)
    report_id = create_report(root, plan.workspace, name or default_name(plan),
                              plan.uut_versions, template, owner=owner)
    return report_id, add_plan(conn, root, report_id, plan, plan.requirements, context,
                               owner=owner, commit=commit)


def reports_for(root, workspace):
    """Reports of `workspace` a selection can be added to (not frozen),
    newest first"""
    if not root or not workspace:
        return []
    return [r for r in store.list_reports(root)
            if r.get("workspace") == workspace and not store.is_frozen(r)]


def passed_combinations(root, report_id):
    """(script, environment, variation) whose latest run in the report
    passed on the report's current UUT versions (an outdated pass isn't)"""
    report = store.load_report(root, report_id)
    by_key = rollup.history(store.list_runs(root, report_id))
    return {
        key for key, runs in by_key.items()
        if runs[0].get("outcome") == "pass" and not rollup.stale_versions(report, runs[0])
    }


def queue_script(conn, root, workspace_root, script, text=None,
                 environment=None, versions=None, workspace="", owner=None, commit=None):
    """Queue one script, in one environment, as a new report.

    The environment defaults to the first the script declares. Every
    variation is queued. `text` overrides the script's content on disk.
    Returns (report_id, first run id).
    """
    from .. import jobs

    closure = resolve(workspace_root, script, text)
    if closure.errors:
        raise jobs.QueueError(closure.errors)
    if environment and environment not in closure.environments:
        raise jobs.QueueError([f"{script} does not support environment {environment}"])
    environment = environment or next(iter(closure.environments), None)

    plan = build_plan(
        workspace,
        workspace_root,
        [script],
        environments=[environment] if environment else None,
        versions=versions,
        texts={script: text} if text is not None else None,
    )
    jobs.check_runnable(plan)  # a script must run: there's nothing to track
    report_id, run_ids = queue_plan(conn, root, plan, owner=owner, commit=commit)
    return report_id, run_ids[0]


class Drift(Exception):
    """No live worker offers the run's environment with its fingerprint.

    `diffs` maps each live worker offering the environment to how its
    fingerprint differs: [(key, then, now)].
    """

    def __init__(self, environment, diffs):
        super().__init__(f"No live worker offers {environment} as it was")
        self.environment = environment
        self.diffs = diffs


def rerun(conn, root, report_id, run_id, force=False, owner=None):
    """Queue the run again, exactly: the same closure, environment,
    variation and UUT versions, as a new run in the same report. A run
    outdated by the report's versions is queued on them instead.

    A run that recorded its environment's fingerprint is rerun only on
    a worker whose environment still has it; if no live worker does,
    Drift is raised. `force` queues it anyway, marked non_identical.
    """
    from .. import jobs

    run = store.load_run(root, report_id, run_id)
    files = store.read_closure(root, report_id, run_id)
    pin, extra = None, {"rerun_of": run_id}
    versions = run.get("uut_versions")
    report = store.load_report(root, report_id) or {}  # scratch has none
    if rollup.stale_versions(report, run):
        current = report["uut_versions"]
        versions = {name: current.get(name, version) for name, version in versions.items()}
        extra["updated_from"] = run.get("uut_versions")
    elif run.get("fingerprint") is not None:
        live = jobs.live_fingerprints(conn, run.get("environment"))
        if run["fingerprint_hash"] in {jobs.fingerprint_hash(fp) for fp in live.values()}:
            pin = run["fingerprint_hash"]
        elif force:
            extra["non_identical"] = True
        else:
            raise Drift(run.get("environment"), {
                url: jobs.fingerprint_diff(run["fingerprint"], fingerprint)
                for url, fingerprint in live.items()
            })
    if "requirement_versions" in run:
        extra["requirement_versions"] = {
            id: v["text_hash"] for id, v in requirement_versions(
                conn, run["requirement_versions"],
                report.get("requirement_context")).items()}
    for kept in ("workspace", "source", "commit"):
        if kept in run:
            extra[kept] = run[kept]
    return jobs.enqueue(conn, root, report_id, run["script"], files,
                        run.get("load_order", [run["script"]]),
                        run.get("environment"), versions,
                        run.get("imports", []), run.get("variation"),
                        fingerprint_hash=pin, owner=owner, **extra)
