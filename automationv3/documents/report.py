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
    .. results::                  :script: PATTERN   :state: pass|fail|...
    .. reruns::
    .. failures::
    .. report-bundle::

and ``:report:`name``` writes one value (see VALUES).
"""

import fnmatch

from docutils.parsers.rst import directives

from .core import directive, role
from .template import Rst, filter, literal, text

ROLLUP_STATES = ["pass", "fail", "error", "incomplete"]


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


@filter
def run_url(row):
    """Where a combination's latest run is, if it has one"""
    latest = row.get("latest")
    if not latest:
        return None
    links = row.get("links")
    return links.run(latest["report_id"], latest["id"]) if links else None


@filter
def why(row):
    """What went wrong with a combination, after its verdict"""
    failure = row.get("failure")
    if failure:
        return Rst((f" at {text(failure['step'])}" if failure["step"] else "")
                   + (f": {text(failure['message'])}" if failure["message"] else ""))
    if row["state"] == "incomplete":
        return Rst(": steps are still to be written (TBD)")
    if row["state"] == "outdated":
        ran = ", ".join(f"{n} {v}" for n, v in sorted(row["outdated"].items()))
        return Rst(f": {text((row['latest'] or {}).get('outcome'))} on {text(ran)}, "
                   "not the report's versions")
    return Rst("")


# The directives

def rows_of(context):
    """The report's combinations, each knowing where its runs link"""
    rows = context.data.combinations
    for row in rows:
        row["links"] = context.data.links
    return rows


def snippet(name):
    def resolve(context, options):
        if context.data is None:
            return ""
        return context.render(f"report/{name}.rst", options=options)
    return resolve


def requirement_results(context, options):
    if context.data is None:
        return ""
    rows_of(context)
    requirements = context.data.requirements
    if options.get("subsystem"):
        requirements = [r for r in requirements if r["subsystem"] == options["subsystem"]]
    if options.get("color"):
        requirements = [r for r in requirements if r["color"] == options["color"]]
    if options.get("group-by", "subsystem") == "none":
        groups = [("", requirements)] if requirements else []
    else:
        by = {}
        for r in requirements:
            by.setdefault(r["subsystem"], []).append(r)
        groups = sorted(by.items(), key=lambda g: (g[0] == "Unassigned", g[0]))
    for r in requirements:
        for cell in r["cells"]:
            cell["links"] = context.data.links
    return context.render("report/requirement-results.rst", groups=groups, options=options)


def results(context, options):
    if context.data is None:
        return ""
    rows = rows_of(context)
    if options.get("script"):
        rows = [r for r in rows if fnmatch.fnmatch(r["script"], options["script"])]
    if options.get("state"):
        rows = [r for r in rows if r["state"] == options["state"]]
    return context.render("report/results.rst", rows=rows, options=options)


def with_rows(name):
    def resolve(context, options):
        if context.data is None:
            return ""
        rows_of(context)
        return context.render(f"report/{name}.rst", options=options)
    return resolve


directive("report-identification", snippet("identification"))
directive("report-summary", snippet("summary"))
directive("open-issues", with_rows("open-issues"))
directive("requirement-results", requirement_results, {
    "group-by": lambda v: directives.choice(v, ("subsystem", "none")),
    "subsystem": directives.unchanged, "color": directives.unchanged})
directive("results", results, {"script": directives.unchanged,
                               "state": directives.unchanged})
directive("reruns", with_rows("reruns"))
directive("failures", with_rows("failures"))
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
        return text(data.report.get("requirement_context") or "trunk")
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
