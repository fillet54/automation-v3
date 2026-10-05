"""Requirement rollups over a report's runs

A report records, for each script it covers, every (environment,
variation) combination a complete run would include, and for each
requirement the scripts referencing it. Each combination is judged on
its latest run:

- red: the latest run of any linked combination failed
- green: the latest run of every linked combination passed
- partial: anything else (not run yet, pending, blocked or error)

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
