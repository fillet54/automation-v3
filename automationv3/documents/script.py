"""A script as one reStructuredText document, with or without a run

The script's statements are grouped as pages show them (grouping.py) and
written as rst: prose as written, each step in a ``step`` container,
titled blocks, definitions and preconditions in ``collapsible``
containers (the first paragraph is their summary), blocks limited to
variations in a ``scoped`` one. With `results`, each step is followed by
the directive its result resolves from (see run.py), so the same
document is a script's page before it runs and a run's page after.
"""

import functools

from ..framework.language import DIRECTIVES, head
from ..framework.statements import get_statements
from . import core
from .grouping import group, statement_item
from .template import Rst, indent, literal, text


def is_step(statement):
    form = statement.statement
    return isinstance(form, list) and head(form) not in DIRECTIVES


def items(statements, diagnostics=()):
    """Statement items (see grouping.statement_item) with their index,
    rst, and the diagnostics about lines they cover (each marked
    "inline", as it shows by its statement)"""
    found = []
    for index, statement in enumerate(statements):
        span = statement.span
        own = [d for d in diagnostics if span is not None and d.get("line") is not None
               and span.line <= d["line"] <= span.end_line]
        for d in own:
            d["inline"] = True
        item = statement_item(statement, index=index, rst=statement.rst,
                              step=is_step(statement), diagnostics=own,
                              source=statement)
        found.append(item)
    return found


def block(classes, summary, body):
    """A container: `summary` first (for collapsible ones), then `body`"""
    parts = [summary] if summary else []
    parts += [b for b in body if b]
    inner = "\n\n".join(indent(Rst(p), 3, first=True) for p in parts)
    return Rst(f".. container:: {classes}\n\n{inner}\n")


def diagnostic(d):
    lines = [f".. container:: diagnostic {d.get('severity', 'error')}", "",
             f"   **{text(str(d.get('severity', 'error')).capitalize())}** {text(d['message'])}"]
    excerpt = d.get("excerpt")
    if excerpt:
        from .run import excerpt_rst
        lines += ["", "   ::", "", indent(excerpt_rst(excerpt), 6, first=True)]
    return Rst("\n".join(lines) + "\n")


def indices(entries):
    """The statement indices an entry list covers"""
    found = []
    for kind, entry in entries:
        if kind in ("statement", "definition"):
            found.append(entry["index"])
        elif kind == "definitions":
            found += [i["index"] for i in entry]
        else:
            found += indices(entry["entries"])
    return found


class Writer:
    def __init__(self, results, variation):
        self.results, self.variation = results, variation

    def item(self, item):
        index = item["index"]
        parts = []
        statement = item["source"]
        if not item["step"] or item["definition"]:
            parts.append(item["rst"])
            if self.results and item["definition"]:
                parts.append(f".. step-result:: {index}\n   :ended-only:\n")
        elif item["precondition"]:
            p = item["precondition"]
            summary = (f"**Precondition** {text(p['name'])}"
                       + (" *(heals)*" if p.get("heal_rst") else "")
                       + (f" :run-state:`{index}`" if self.results else ""))
            if self.results:
                body = [f".. precondition-result:: {index}"]
            else:
                body = ["**Check**", p["check_rst"]]
                if p.get("heal_rst"):
                    body += [f"**If not, heal by** {text(p.get('heal_name') or '')}",
                             p["heal_rst"]]
            parts.append(block("precondition collapsible", summary, body))
        elif statement.table_rows:
            parts.append(item["rst"])
            if self.results:
                parts.append(f".. table-results:: {index}")
        else:
            parts.append(block("step", None, [item["rst"],
                               f".. step-result:: {index}" if self.results else ""]))
        parts += [diagnostic(d) for d in item["diagnostics"]]
        return "\n\n".join(parts)

    def entries(self, entries):
        return "\n\n".join(p for p in (self.entry(kind, e) for kind, e in entries) if p)

    def entry(self, kind, entry):
        if kind == "statement":
            return self.item(entry)
        if kind == "definitions":
            names = ", ".join(i["defines"] for i in entry if i["defines"])
            return block("definitions collapsible",
                         f"**Definitions** {literal(names) if names else ''}",
                         [self.item(i) for i in entry])
        if kind == "definition":
            return block("definition collapsible",
                         f"**Definition** {literal(entry['defines'])}", [self.item(entry)])
        if kind == "titled":
            covered = indices(entry["entries"])
            state = (f" :run-state:`{min(covered)}-{max(covered)}`"
                     if self.results and covered else "")
            todo = " :verdict:`tbd`" if entry.get("todo") and not self.results else ""
            return block("titled collapsible", f"**{text(entry['title'])}**{state}{todo}",
                         [self.entries(entry["entries"])])
        if kind == "scoped":
            if self.variation and self.variation not in entry["variations"]:
                return ""
            only = " ".join(literal(v) for v in entry["variations"])
            return block("scoped", f"*Only for* {only}", [self.entries(entry["entries"])])
        raise ValueError(kind)


def source(statements, variation=None, results=False, diagnostics=(), variations=True):
    """The rst of a script's document. With `results`, steps are followed
    by their result directives, and a table block's steps go with its
    rows; with `variation`, only what that variation runs is shown.
    Without `variations`, the variations form is left out (pages show it
    with the script's details)."""
    found = items(statements, diagnostics)
    if not variations:
        found = [i for i in found if i["directive"] != "variations"]
    if results:
        found = [i for i in found
                 if not (i["source"].table is not None and not i["source"].table_rows)]
        if variation:
            found = [i for i in found
                     if not (i["variations"] and variation not in i["variations"])]
    return Writer(results, variation).entries(group(found, variation))


@functools.lru_cache(maxsize=64)
def _parsed(text_, variation, results, variations, requirement_key):
    return core.parse(source(get_statements(text_), variation, results, (), variations),
                      source_path="<script>")


def parsed(text_, variation=None, results=False, diagnostics=(), variations=True):
    """The parsed (unresolved) document of a script's text: cached, unless
    it carries diagnostics"""
    from ..framework import rst as script_rst
    if diagnostics:
        return core.parse(source(get_statements(text_), variation, results, diagnostics,
                                 variations), source_path="<script>")
    return _parsed(text_, variation, results, variations, script_rst.requirement_key())
