"""Grouping a script's rendered statements for display

The definitions section shows as one collapsed block, and any other
definition as its own collapsed line; everything else as it is.
Consecutive statements limited to the same variations are kept together
as one scoped entry, so a page can tag or collapse them as a unit.
"""

from ..framework.closure import head


def group(items):
    """Entries of ("statement", item), ("definitions", [items]),
    ("definition", item) or ("scoped", {"variations", "entries"}), the
    last holding entries of the first three kinds. `items` have
    in_definitions / definition / variations."""
    entries, run = [], []
    for item in items + [None]:
        if run and (item is None or item["variations"] != run[0]["variations"]):
            if run[0]["variations"] is None:
                entries.extend(group_definitions(run))
            else:
                entries.append(("scoped", {"variations": run[0]["variations"],
                                           "entries": group_definitions(run)}))
            run = []
        if item is not None:
            run.append(item)
    return entries


def group_definitions(items):
    entries = []
    for item in items:
        if item["in_definitions"]:
            if entries and entries[-1][0] == "definitions":
                entries[-1][1].append(item)
            else:
                entries.append(("definitions", [item]))
        elif item["definition"]:
            entries.append(("definition", item))
        else:
            entries.append(("statement", item))
    return entries


def statement_item(statement, **extra):
    return {
        "html": statement.html,
        "in_definitions": statement.in_definitions,
        "definition": statement.definition,
        "defines": statement.defines,
        "variations": statement.variations,
        "directive": head(statement.statement),
        **extra,
    }
