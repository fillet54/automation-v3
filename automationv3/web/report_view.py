"""What a report's pages show: its navigation tree by subsystem,
requirement and script, with a status dot for each, and why each one
that didn't pass didn't

The navigation builds one tree::

    subsystem -> requirement -> script

plus "Other tests" for scripts added without a requirement. Every node
has a `dot` for its state and the groups an `issues` count. A tracked
requirement no script references yet is "untested": it has no scripts.
"""

import re

from ..documents.report import (
    UNASSIGNED,
    failure_reason,
    outdated_label,
    versions_text,  # noqa: F401
)
from ..framework import source
from ..services.reports import rollup

OTHER = "Other tests"

# A dot's tone for each state: what a reader should do about it
DOTS = {
    "pass": "pass", "green": "pass",
    "fail": "fail", "error": "fail", "red": "fail",
    "incomplete": "partial", "tbd": "partial", "partial": "partial",
    "blocked": "partial", "released": "partial", "unknown": "partial",
    "running": "running", "claimed": "running",
    "pending": "none", "not run": "none", "untested": "none",
    "outdated": "partial",
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


def build(data, lookup=None):
    """Everything a report's pages show, from a `ReportData`.
    `lookup(ids)` gives {id: (text, subsystem)} for requirements the
    report didn't record."""
    requirements = data.requirements
    missing = [r["id"] for r in requirements
               if not r["text"] or not r["snapshot"].get("subsystem")]
    looked_up = lookup(missing) if lookup and missing else {}

    titles = {}
    rows = [
        {
            **row,
            "title": script_title(data, row, titles),
            "dot": dot(row["state"]),
            "why": why(row, data.uut_versions),
            "label": outdated_label(row),
        }
        for row in data.combinations
    ]

    by_script = {}
    for row in rows:
        by_script.setdefault(row["script"], []).append(row)

    tree, tracked = {}, set()
    for requirement in requirements:
        req_id = requirement["id"]
        scripts = requirement["scripts"]
        tracked.update(scripts)
        extra_text, extra_subsystem = looked_up.get(req_id, ("", None))
        req_text = requirement["text"] or extra_text
        subsystem = (requirement["snapshot"].get("subsystem")
                     or extra_subsystem or UNASSIGNED)
        entry = {
            "id": req_id,
            "text": req_text,
            "subsystem": subsystem,
            "color": requirement["color"],
            "passed": requirement["passed"],
            "total": requirement["total"],
            "scripts": [script_entry(req_id, script, by_script.get(script), titles)
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
        "duration": None, "why": None, "label": None, "outdated": {},
        "title": titles.get(script) or script,
    }]
    return {
        "script": script,
        "title": titles.get(script) or script,
        "anchor": script_anchor(requirement, script),
        "rows": rows,
        "dot": worst(r["dot"] for r in rows),
        "issues": sum(1 for r in rows if r["dot"] != "pass"),
    }


def script_title(data, row, titles):
    """The script's title (its document's first heading), from the
    closure its latest run executed; else its file name"""
    script = row["script"]
    if script not in titles:
        text = data.script_text(row["latest"]) if row["latest"] else ""
        titles[script] = (text and source.title(source.parse(text))) or None
    return titles[script] or script.rsplit("/", 1)[-1]


def why(row, uut_versions=None):
    """A short reason a combination didn't pass, or None"""
    return failure_reason(row, uut_versions)


def connector_group(path):
    """A ref's group: its path's first two parts (the UUT's handle and
    the connector group, e.g. lm.eps), or all but its last part"""
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
        "outdated": states.count("outdated"),
        "combinations": len(states),
        "in_progress": any(run.get("outcome") is None for run in runs),
    }
