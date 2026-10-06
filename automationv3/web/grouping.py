"""Grouping a script's rendered statements for display

The definitions section shows as one collapsed block, and any other
definition as its own collapsed line; everything else as it is.
A titled rvt block's statements are kept together as one titled entry,
which pages show collapsed to the title. Consecutive statements limited
to the same variations are kept together as one scoped entry, so a page
can tag or collapse them as a unit.
"""

from itertools import groupby

from ..framework.closure import head

# A titled block's state is its most telling step's: earlier wins
STATE_ORDER = ["fail", "running", "pending", "not run", "pass"]


def group(items):
    """Entries of ("statement", item), ("definitions", [items]),
    ("definition", item), ("titled", {"title", "state", "entries"}) or
    ("scoped", {"variations", "entries"}). Scoped entries hold any of
    the others; titled entries hold the first three kinds. `items` have
    in_definitions / definition / variations / block / title."""
    entries = []
    for variations, run in groupby(items, key=lambda item: item["variations"]):
        inner = group_blocks(list(run))
        if variations is None:
            entries.extend(inner)
        else:
            entries.append(("scoped", {"variations": variations, "entries": inner}))
    return entries


def titled_block(item):
    """The (block, title) of a titled block's statement, else None. The
    definitions section is already collapsed, so its titles aren't used."""
    if item["title"] and not item["in_definitions"]:
        return item["block"], item["title"]
    return None


def group_blocks(items):
    entries = []
    for key, run in groupby(items, key=titled_block):
        run = list(run)
        if key is None:
            entries.extend(group_definitions(run))
        else:
            entries.append(("titled", {"title": key[1], "state": block_state(run),
                                       "entries": group_definitions(run)}))
    return entries


def block_state(items):
    """The state of a titled block's steps, None if it has no results"""
    states = [item["state"] for item in items if item.get("step") and "state" in item]
    return min(states, key=STATE_ORDER.index) if states else None


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
        "block": statement.block,
        "title": statement.title,
        **extra,
    }
