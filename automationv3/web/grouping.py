"""Grouping a script's rendered statements for display

The definitions section shows as one collapsed block, and any other
definition as its own collapsed line; everything else as it is.
"""


def group(items):
    """Entries of ("statement", item), ("definitions", [items]) or
    ("definition", item). `items` have in_definitions / definition."""
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
        **extra,
    }
