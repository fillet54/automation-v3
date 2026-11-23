"""The report directives, its :report: role, and the filters their
snippets use (snippets/report/)

A report's document is its report.rst: prose, and these directives where
the report's data goes. Each renders a snippet of the same name from the
report's data (a services.reports.data.ReportData)::

    .. report-identification::
    .. report-summary::
    .. open-issues::
    .. requirement-results::      :group-by: subsystem|none
                                  :subsystem: NAME   :color: green|red|...
    .. script-results::
    .. results::                  :script: PATTERN   :state: pass|fail|...
    .. reruns::
    .. failures::
    .. report-bundle::

and ``:report:`name``` writes one value (see VALUES).
"""

import fnmatch

import jinja2
from docutils.parsers.rst import directives

from .core import directive, role
from .template import Rst, filter, link, literal, plural, text

UNASSIGNED = "Unassigned"
ROLLUP_STATES = ["pass", "fail", "error", "incomplete"]
# Worst first: a group of combinations is as bad as its worst
WORST = ["fail", "error", "outdated", "incomplete", "blocked", "not run",
         "pending", "running", "unfinished", "pass"]
WORDS = {"pass": "passed", "fail": "failed", "error": "stopped on an error",
         "incomplete": "incomplete", "not run": "not run", "outdated": "outdated",
         "blocked": "blocked", "pending": "pending", "running": "running"}
OUTCOME_TITLES = {"pass": "Passed", "fail": "Failed", "error": "Error",
                  "incomplete": "Incomplete", "blocked": "Blocked"}
COLORS = ["red", "partial", "untested", "green"]


def rank(state):
    return WORST.index(state) if state in WORST else WORST.index("pass") - 0.5


def worst(states):
    return min(states, key=rank) if states else "not run"


def combination_key(row):
    return (row["script"], row["environment"], row["variation"])


def versions_text(versions):
    return ", ".join(f"{name} {id}" for name, id in sorted(versions.items()))


def outdated_label(row):
    """'Passed on lm LUM131' for an outdated combination, else None"""
    if row["state"] != "outdated":
        return None
    word = OUTCOME_TITLES.get((row.get("latest") or {}).get("outcome"), "Ran")
    return f"{word} on {versions_text(row['outdated'])}"


def ran_on(row):
    """'fail on lm LUM131': how an outdated combination's latest run came
    out ('ran' if it has no outcome yet), and on what"""
    outcome = (row.get("latest") or {}).get("outcome")
    return f"{outcome or 'ran'} on {versions_text(row['outdated'])}"


NOT_CURRENT = "not the report's versions"
TBD = "steps are still to be written (TBD)"


def failure_reason(row, uut_versions=None):
    """Plain-text reason a combination didn't pass, or None"""
    state = row["state"]
    if state == "outdated":
        current = uut_versions or {}
        now = {name: current[name]["id"] for name in row["outdated"] if name in current}
        if now:
            return (f"{outdated_label(row)}; the report is on {versions_text(now)}. "
                    "Rerun it, or Update tests, to bring it up to date.")
        return f"{outdated_label(row)}, {NOT_CURRENT}"
    if state in ("fail", "error") and row.get("failure"):
        found = row["failure"]
        parts = [p for p in (found["step"], found["message"]) if p]
        return ": ".join(parts) or None
    if state == "incomplete":
        return TBD[0].upper() + TBD[1:]
    if state == "not run":
        return "Not run in this report"
    if state == "blocked":
        return "A precondition couldn't be met"
    return None


# Filters for report snippets

@filter
def uut_versions(data):
    return ", ".join(f"{name} {v['id']} ({v.get('digest', '')[:12]})"
                     for name, v in data.used_uut_versions().items())


@filter
def environments(data):
    return "; ".join(f"{env or 'none'}: {', '.join(p) or 'platform not recorded'}"
                     for env, p in data.environments().items())


@filter
def states(rows):
    """The states to count: the usual four, then any others there are"""
    return list(dict.fromkeys([*ROLLUP_STATES, *(r["state"] for r in rows)]))


@filter
def combination_name(row):
    return " / ".join(p for p in (row["script"], row["environment"], row["variation"]) if p)


def _run_url(row, links):
    latest = row.get("latest")
    if not latest or not links:
        return None
    return links.run(latest["report_id"], latest["id"])


@filter
@jinja2.pass_context
def run_url(ctx, row, links=None):
    """Where a combination's latest run is, if it has one"""
    if links is None:
        data = ctx.get("data")
        links = data.links if data else None
    return _run_url(row, links)


@filter
def why(row):
    """What went wrong with a combination, after its verdict"""
    failure = row.get("failure")
    if failure:
        return Rst((f" at {text(failure['step'])}" if failure["step"] else "")
                   + (f": {text(failure['message'])}" if failure["message"] else ""))
    if row["state"] == "incomplete":
        return Rst(f": {TBD}")
    if row["state"] == "outdated":
        return Rst(f": {text(ran_on(row))}, {NOT_CURRENT}")
    return Rst("")


@filter
def by_script(cells):
    """Combinations grouped by script, in order: [{"script", "cells",
    "state" (the worst of them), "passed", "total"}]. Each cell gets a
    "label": its variation, after its environment when the script ran in
    more than one."""
    groups = {}
    for cell in cells:
        groups.setdefault(cell["script"], []).append(cell)
    found = []
    for script, group in groups.items():
        environments = {c["environment"] for c in group}
        labeled = [
            {**c, "label": " / ".join(p for p in (
                c["environment"] if len(environments) > 1 else None,
                c["variation"]) if p)}
            for c in group
        ]
        states = [c["state"] for c in labeled]
        found.append({"script": script, "cells": labeled, "state": worst(states),
                      "passed": states.count("pass"), "total": len(states)})
    return found


@filter
def tally(group):
    """How a script's combinations came out, in words: "passed", "all 4
    passed", "1 failed, 1 passed" """
    counts = {}
    for cell in group["cells"]:
        counts[cell["state"]] = counts.get(cell["state"], 0) + 1
    if list(counts) == ["pass"]:
        return "passed" if group["total"] == 1 else f"all {group['total']} passed"
    if len(counts) == 1 and group["total"] == 1:
        return WORDS.get(group["state"], group["state"])
    return ", ".join(f"{n} {WORDS.get(state, state)}"
                     for state, n in sorted(counts.items(), key=lambda kv: rank(kv[0])))


@filter
@jinja2.pass_context
def issue(ctx, cell, links=None):
    """One combination that didn't pass, briefly: how it came out
    (linking its run) and, for a failure, at which step"""
    if links is None:
        data = ctx.get("data")
        links = data.links if data else None
    said = link(WORDS.get(cell["state"], cell["state"]), _run_url(cell, links))
    failure = cell.get("failure") or {}
    if failure.get("step"):
        said = Rst(f"{said} at {text(failure['step'])}")
    elif cell["state"] == "incomplete":
        said = Rst(f"{said} (steps still to be written)")
    elif cell["state"] == "outdated":
        said = Rst(f"{said}: {text(ran_on(cell))}, {NOT_CURRENT}")
    return said


@filter
def variations(group):
    """A script's variations for the scripts table: how many, and how they
    came out when not all alike"""
    if len({c["state"] for c in group["cells"]}) == 1:
        return str(group["total"])
    return f"{group['total']}: {tally(group)}"


@filter
def open_requirements(requirements):
    """The requirements that aren't green, red first"""
    return sorted((r for r in requirements if r["color"] != "green"),
                  key=lambda r: COLORS.index(r["color"]) if r["color"] in COLORS else 0)


@filter
def covers(row, requirements):
    """The requirements a combination counts toward"""
    key = combination_key(row)
    return [r for r in requirements
            if any(combination_key(c) == key for c in r["cells"])]


@filter
def summary_text(data):
    """The report's outcome in a sentence or two"""
    requirements, rows = data.requirements, data.combinations
    n = {color: sum(1 for r in requirements if r["color"] == color) for color in COLORS}
    if not requirements:
        said = "The report tracks no requirements."
    elif n["green"] == len(requirements):
        said = f"All {plural(len(requirements), 'requirement')} pass."
    else:
        parts = []
        if n["red"]:
            parts.append(f"{n['red']} fail" if n["red"] > 1 else "1 fails")
        if n["partial"]:
            parts.append(f"{n['partial']} {'are' if n['partial'] > 1 else 'is'} not fully verified")
        if n["untested"]:
            parts.append(f"{n['untested']} {'have' if n['untested'] > 1 else 'has'} no tests")
        listed = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
        said = (f"Of {plural(len(requirements), 'requirement')}, {listed}"
                + ("; none pass." if not n["green"] else "; the other one passes."
                   if n["green"] == 1 else f"; the other {n['green']} pass."))
    scripts = by_script(rows)
    ran = sum(1 for run in data.runs if run.get("outcome"))
    versions = ", ".join(f"{name} {v['id']}" for name, v in data.used_uut_versions().items())
    said += (f" It has {plural(len(scripts), 'script')}, run {plural(ran, 'time')}"
             + (f" on {versions}" if versions else "") + ".")
    counts = {}
    for g in scripts:
        if g["state"] != "pass":
            counts[g["state"]] = counts.get(g["state"], 0) + 1
    if counts:
        parts = [f"{n} {WORDS.get(state, state)}"
                 for state, n in sorted(counts.items(), key=lambda kv: rank(kv[0]))]
        listed = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
        said += f" Of those scripts, {listed}; the rest passed."
    return text(said)


# The directives

def snippet(name):
    def resolve(context, options):
        if context.data is None:
            return ""
        return context.render(f"report/{name}.rst", options=options)
    return resolve


def requirement_results(context, options):
    if context.data is None:
        return ""
    changed = context.extra.get("text_changed") or set()
    requirements = [
        {**r, "changed": r["id"] in changed}
        for r in context.data.requirements
    ]
    # A page may narrow every requirement-results to one subsystem
    subsystem = options.get("subsystem") or context.extra.get("subsystem")
    if subsystem:
        requirements = [r for r in requirements if r["subsystem"] == subsystem]
    if options.get("color"):
        requirements = [r for r in requirements if r["color"] == options["color"]]
    if options.get("group-by", "subsystem") == "none":
        groups = [("", requirements)] if requirements else []
    else:
        by = {}
        for r in requirements:
            by.setdefault(r["subsystem"], []).append(r)
        groups = sorted(by.items(), key=lambda g: (g[0] == UNASSIGNED, g[0]))
    return context.render("report/requirement-results.rst", groups=groups, options=options)


def results(context, options):
    if context.data is None:
        return ""
    rows = context.data.combinations
    if options.get("script"):
        rows = [r for r in rows if fnmatch.fnmatch(r["script"], options["script"])]
    if options.get("state"):
        rows = [r for r in rows if r["state"] == options["state"]]
    return context.render("report/results.rst", rows=rows, options=options)


directive("report-identification", snippet("identification"))
directive("report-summary", snippet("summary"))
directive("open-issues", snippet("open-issues"))
directive("requirement-results", requirement_results, {
    "group-by": lambda v: directives.choice(v, ("subsystem", "none")),
    "subsystem": directives.unchanged, "color": directives.unchanged})
directive("script-results", snippet("script-results"))
directive("results", results, {"script": directives.unchanged,
                               "state": directives.unchanged})
directive("reruns", snippet("reruns"))
directive("failures", snippet("failures"))
directive("report-bundle", snippet("bundle"))


# :report:`name`

def count(items, key, value):
    return str(sum(1 for i in items if i[key] == value))


def value(context, name):
    """The value :report:`name` writes, as inline rst"""
    data = context.data
    if data is None:
        return literal(name)
    document = data.document
    if name in ("title", "name"):
        return text(data.name)
    if name in ("number", "revision", "author"):
        return text(document[name] or "-")
    if name == "id":
        return literal(data.id)
    if name == "context":
        return text(data.requirement_context)
    if name == "runs":
        return text(len(data.runs))
    if name == "requirements":
        return text(len(data.requirements))
    if name.startswith("requirements."):
        return text(count(data.requirements, "color", name.split(".", 1)[1]))
    if name == "combinations":
        return text(len(data.combinations))
    if name.startswith("combinations."):
        return text(count(data.combinations, "state", name.split(".", 1)[1]))
    if name.startswith("uut."):
        version = data.uut_versions.get(name.split(".", 1)[1])
        return text(version["id"]) if version else text("-")
    if name in ("first_run", "last_run"):
        from .template import stamp
        return text(stamp(getattr(data, name)) or "-")
    return Rst(f"**unknown report value {text(name)}**")


VALUES = ("title", "number", "revision", "author", "id", "context", "runs",
          "requirements", "requirements.<color>", "combinations",
          "combinations.<state>", "uut.<name>", "first_run", "last_run")

role("report", value)
