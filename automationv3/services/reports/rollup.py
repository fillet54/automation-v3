"""Requirement rollups over a report's runs

A report records, for each script it covers, every (environment,
variation) combination a complete run would include, and for each
requirement the scripts referencing it. Each combination is judged on
its latest run:

- red: the latest run of any linked combination failed
- green: the latest run of every linked combination passed
- partial: anything else (not run yet, pending, blocked, error, or
  incomplete: a script with steps still to be written)

Linked scripts that weren't queued, and variations that were left out,
count as not run.
"""


def run_key(run):
    variation = run.get("variation") or {}
    return (run["script"], run.get("environment"), variation.get("name"))


def expected_combos(report):
    """script -> [(environment, variation)] a complete report covers"""
    combos = {}
    for entry in report.get("scripts", []):
        if isinstance(entry, dict):
            combos[entry["script"]] = [tuple(c) for c in entry.get("expected", [])]
    return combos


def history(runs):
    """key -> runs for that key, newest first"""
    by_key = {}
    for run in runs:  # oldest first
        by_key.setdefault(run_key(run), []).insert(0, run)
    return by_key


def state_of(run, status):
    if run is None:
        return "not run"
    return run.get("outcome") or status(run)


def combinations(report, runs, status):
    """Every combination with its latest run and earlier reruns.

    Combinations the report expected come first, in report order, then
    any others that have runs (e.g. reports from before plans existed).
    """
    by_key = history(runs)
    keys = [
        (script, *combo)
        for script, combos in expected_combos(report).items()
        for combo in combos
    ]
    keys += [key for key in by_key if key not in keys]
    rows = []
    for key in keys:
        runs_for_key = by_key.get(key, [])
        latest = runs_for_key[0] if runs_for_key else None
        rows.append({
            "script": key[0],
            "environment": key[1],
            "variation": key[2],
            "latest": latest,
            "earlier": runs_for_key[1:],
            "state": state_of(latest, status),
        })
    return rows


def color(states):
    if "fail" in states:
        return "red"
    if states and all(state == "pass" for state in states):
        return "green"
    return "partial"


def requirement_rollup(report, rows):
    """One entry per requirement: its color and its combinations"""
    by_script = {}
    for row in rows:
        by_script.setdefault(row["script"], []).append(row)
    rollup = []
    for requirement, scripts in sorted(report.get("requirements", {}).items()):
        cells = []
        for script in scripts:
            cells.extend(by_script.get(script) or [{
                "script": script, "environment": None, "variation": None,
                "latest": None, "earlier": [], "state": "not run",
            }])
        states = [cell["state"] for cell in cells]
        rollup.append({
            "id": requirement,
            "color": color(states),
            "passed": states.count("pass"),
            "total": len(states),
            "cells": cells,
        })
    return rollup


# Refs: which values a run touched, and across a report, which each
# requirement's scripts touched

OPERATIONS = ("read", "set", "fix", "clear")


def touched(events):
    """The refs a run's events say it touched, by path: [{"path", "name",
    "type", "operations", "steps"}], sorted by path. `name` is the first
    name the script reached it by; `type` the kind of ref."""
    found = {}
    for event in events:
        if event.get("kind") != "ref":
            continue
        entry = found.setdefault((event.get("type"), event["path"]), {
            "path": event["path"], "name": event.get("name") or event["path"],
            "type": event.get("type"), "operations": set(), "steps": set(),
        })
        entry["operations"].add(event["operation"])
        if event.get("index") is not None:
            entry["steps"].add(event["index"])
    return [
        {**entry,
         "operations": [op for op in OPERATIONS if op in entry["operations"]],
         "steps": sorted(entry["steps"])}
        for _, entry in sorted(found.items(), key=lambda item: item[0][1])
    ]


def ref_rollup(report, rows, events_of):
    """Every ref the latest runs of a report touched: [{"path", "type",
    "operations", "scripts", "requirements"}], sorted by path.
    `events_of(run)` gives a run's events."""
    requirements_of = {}
    for requirement, scripts in report.get("requirements", {}).items():
        for script in scripts:
            requirements_of.setdefault(script, set()).add(requirement)
    found = {}
    for row in rows:
        if not row.get("latest"):
            continue
        for entry in touched(events_of(row["latest"])):
            rolled = found.setdefault((entry["type"], entry["path"]), {
                "path": entry["path"], "type": entry["type"], "operations": set(),
                "scripts": set(), "requirements": set()})
            rolled["operations"].update(entry["operations"])
            rolled["scripts"].add(row["script"])
            rolled["requirements"].update(requirements_of.get(row["script"], ()))
    return [
        {"path": r["path"], "type": r["type"],
         "operations": [op for op in OPERATIONS if op in r["operations"]],
         "scripts": sorted(r["scripts"]),
         "requirements": sorted(r["requirements"])}
        for _, r in sorted(found.items(), key=lambda item: item[0][1])
    ]
