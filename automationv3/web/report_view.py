"""What a report's pages show: its runs rolled up by subsystem,
requirement and script, with a status for each, and why each one that
didn't pass didn't

The Runs page and its navigation share one tree::

    subsystem -> requirement -> script

plus "Other tests" for scripts added without a requirement. Every node
has a `dot` for its state and the groups an `issues` count. A tracked
requirement no script references yet is "untested": it has no scripts.
"""

import re

from ..framework.document import document_title
from ..services.reports import export, rollup, store

UNASSIGNED = "Unassigned"
OTHER = "Other tests"

# A dot's tone for each state: what a reader should do about it
DOTS = {
    "pass": "pass", "green": "pass",
    "fail": "fail", "error": "fail", "red": "fail",
    "incomplete": "partial", "tbd": "partial", "partial": "partial",
    "blocked": "partial", "released": "partial", "unknown": "partial",
    "running": "running", "claimed": "running",
    "pending": "none", "not run": "none", "untested": "none",
}

# Worst first: a group takes the worst state of what it holds
WORST = ["fail", "running", "partial", "none", "pass"]


def dot(state):
    return DOTS.get(state, "partial")


def worst(dots):
    dots = list(dots)
    return min(dots, key=WORST.index) if dots else "none"


def slug(text):
    return re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-")


def script_anchor(requirement, script):
    return f"{slug(requirement or 'other')}--{slug(script)}"


def build(root, report, runs, status, lookup=None):
    """Everything a report's pages show. `status(run)` is a run's state
    while it has no outcome; `lookup(ids)` gives {id: (text, subsystem)}
    for requirements the report didn't record."""
    rows = rollup.combinations(report, runs, status)
    requirements = rollup.requirement_rollup(report, rows)
    texts = dict(report.get("requirement_texts") or {})
    subsystems = dict(report.get("requirement_subsystems") or {})
    missing = [r["id"] for r in requirements
               if r["id"] not in texts or r["id"] not in subsystems]
    for id, (text, subsystem) in (lookup(missing) if lookup and missing else {}).items():
        texts.setdefault(id, text)
        if subsystem:
            subsystems.setdefault(id, subsystem)

    titles = {}
    for row in rows:
        row["title"] = script_title(root, report["id"], row, titles)
        row["dot"] = dot(row["state"])
        row["attempts"] = len(row["earlier"]) + (1 if row["latest"] else 0)
        row["duration"] = export.duration(row["latest"])
        row["why"] = why(root, row)

    by_script = {}
    for row in rows:
        by_script.setdefault(row["script"], []).append(row)

    tree, tracked = {}, set()
    for requirement in requirements:
        scripts = report.get("requirements", {}).get(requirement["id"], [])
        tracked.update(scripts)
        entry = {
            "id": requirement["id"],
            "text": texts.get(requirement["id"], ""),
            "subsystem": subsystems.get(requirement["id"]) or UNASSIGNED,
            "color": requirement["color"],
            "passed": requirement["passed"],
            "total": requirement["total"],
            "scripts": [script_entry(requirement["id"], script, by_script.get(script), titles)
                        for script in scripts],
        }
        script_dots = [s["dot"] for s in entry["scripts"]]
        if script_dots and all(d == "none" for d in script_dots):
            entry["dot"] = "none"  # nothing ran: not run, rather than partial
        else:
            entry["dot"] = worst([dot(requirement["color"]),
                                  *(d for d in script_dots if d == "running")])
        entry["issues"] = sum(1 for s in entry["scripts"] if s["dot"] != "pass")
        tree.setdefault(entry["subsystem"], []).append(entry)

    groups = []
    for name in sorted(tree, key=lambda n: (n == UNASSIGNED, n)):
        entries = tree[name]
        groups.append({
            "name": name,
            "requirements": entries,
            "dot": worst(e["dot"] for e in entries),
            "issues": sum(1 for e in entries if e["dot"] != "pass"),
            "green": sum(1 for e in entries if e["color"] == "green"),
            "untested": sum(1 for e in entries if e["color"] == "untested"),
        })

    others = [script_entry(None, script, script_rows, titles)
              for script, script_rows in by_script.items() if script not in tracked]
    other = None
    if others:
        other = {"name": OTHER, "scripts": others,
                 "dot": worst(s["dot"] for s in others),
                 "issues": sum(1 for s in others if s["dot"] != "pass")}

    return {
        "dot": worst([*(g["dot"] for g in groups), *([other["dot"]] if other else [])]),
        "rows": rows,
        "requirements": requirements,
        "groups": groups,
        "other": other,
        "issues": [row for row in rows if row["dot"] != "pass"],
        "untested": [e for g in groups for e in g["requirements"]
                     if e["color"] == "untested"],
    }


def script_entry(requirement, script, rows, titles):
    rows = rows or [{
        "script": script, "environment": None, "variation": None, "latest": None,
        "earlier": [], "state": "not run", "dot": "none", "attempts": 0,
        "duration": None, "why": None, "title": titles.get(script) or script,
    }]
    return {
        "script": script,
        "title": titles.get(script) or script,
        "anchor": script_anchor(requirement, script),
        "rows": rows,
        "dot": worst(r["dot"] for r in rows),
        "issues": sum(1 for r in rows if r["dot"] != "pass"),
    }


def script_title(root, report_id, row, titles):
    """The script's title (its document's first heading), from the
    closure its latest run executed; else its file name"""
    script = row["script"]
    if script not in titles:
        text = None
        if row["latest"]:
            text = store.read_closure_file(root, report_id, row["latest"]["id"], script)
        titles[script] = (text and document_title(text)) or None
    return titles[script] or script.rsplit("/", 1)[-1]


def why(root, row):
    """A short reason a combination didn't pass, or None"""
    state, run = row["state"], row["latest"]
    if state in ("fail", "error") and run:
        found = export.failure(root, run)
        parts = [p for p in (found["step"], found["message"]) if p]
        return ": ".join(parts) or None
    if state == "incomplete":
        return "Steps are still to be written (TBD)"
    if state == "not run":
        return "Not run in this report"
    if state == "blocked":
        return "A precondition couldn't be met"
    return None


def connector_group(path):
    """A ref's group: its path's first two parts (the UUT's handle and
    the connector group, e.g. vm.eps), or all but its last part"""
    parts = re.split(r"[./]", path)
    return ".".join(parts[:2] if len(parts) > 2 else parts[:-1] or parts)


def connectors(touched):
    """The refs the latest runs touched, by group (see connector_group):
    [{"name", "anchor", "refs", "fixed"}], fixed refs first in each"""
    groups = {}
    for ref in touched:
        groups.setdefault(connector_group(ref["path"]), []).append(ref)
    return [
        {"name": name, "anchor": f"connector-{slug(name)}",
         "refs": sorted(refs, key=lambda r: ("fix" not in r["operations"], r["path"])),
         "fixed": sum(1 for r in refs if "fix" in r["operations"])}
        for name, refs in sorted(groups.items())
    ]


def summary(report, runs):
    """A report's figures for the list of reports: its requirements by
    color, and its combinations by how their latest run came out"""
    rows = rollup.combinations(report, runs, lambda run: "pending")
    colors = [r["color"] for r in rollup.requirement_rollup(report, rows)]
    states = [row["state"] for row in rows]
    return {
        "requirements": {c: colors.count(c) for c in ("green", "red", "partial", "untested")},
        "requirements_total": len(colors),
        "passed": states.count("pass"),
        "failed": sum(1 for s in states if s in ("fail", "error")),
        "combinations": len(states),
        "in_progress": any(run.get("outcome") is None for run in runs),
    }
