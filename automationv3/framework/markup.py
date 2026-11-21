"""reStructuredText helpers for blocks and forms that render themselves

Blocks write rst (see BuildingBlock.as_rst), so a step reads the same on a
page, in a static site and in a PDF. These helpers escape values, so a
value never turns into markup, and write the constructs blocks use most.
"""

import re

from . import edn


class Rst(str):
    """Text that is already reStructuredText"""


# Inline markup that could start anywhere: emphasis, literals,
# interpreted text and substitutions; and a reference's closing "_"
INLINE = re.compile(r"([\\`*|])|_(?=\W|$)")
# What could open a block at the start of a line: a bullet or
# enumerated list, a field, a comment or directive, a line block
BLOCK = re.compile(r"[-+*•|]( |$)|:|(\d+|[a-zA-Z#]|[ivxlcdmIVXLCDM]+)[.)]( |$)"
                   r"|\(\w+\)( |$)|\.\.( |$)|>>>")


def escape_text(value):
    """`value` on one line, as plain rst text: nothing in it is markup"""
    value = " ".join(str(value if value is not None else "").split())
    value = INLINE.sub(lambda m: "\\" + m.group(0), value)
    if BLOCK.match(value) or (len(value) > 1 and len(set(value)) == 1
                              and not value[0].isalnum()):
        value = "\\" + value  # not a list, nor a heading's underline
    if value.endswith("::"):
        value = value[:-1] + "\\:"  # not the start of a literal block
    return Rst(value)


def literal(value):
    """`value` as inline literal text"""
    value = " ".join(str(value if value is not None else "").split())
    return Rst(f"``{value.replace('``', '` `')}``" if value else "")


def indent(value, width=3, first=False):
    """`value`'s lines indented by `width` (the first too, if `first`),
    blank lines left blank; escaped first unless it is Rst"""
    value = value if isinstance(value, Rst) else escape_text(value)
    pad = " " * width
    lines = value.split("\n")
    return Rst("\n".join(
        (pad + line if line.strip() and (n or first) else line)
        for n, line in enumerate(lines)))


def heading(title, char="="):
    """A section title and its underline"""
    title = escape_text(title)
    return Rst(f"{title}\n{char * max(len(title), 1)}")


def written(value):
    """A value as written in a script: strings as they are, everything
    else (keywords, symbols, numbers, collections) as edn"""
    if isinstance(value, str) and not isinstance(value, (edn.Symbol, edn.Keyword)):
        return value
    return edn.writes(value)


def text(value):
    """A value as plain text"""
    return escape_text(written(value))


def code(*values):
    """Values as inline code, separated by spaces"""
    return literal(" ".join(edn.writes(v) for v in values))


def strong(value):
    value = escape_text(value)
    return Rst(f"**{value}**") if value else value


def line(*parts):
    """Parts (rst, or text to escape) joined by spaces into one line"""
    return Rst(" ".join(p if isinstance(p, Rst) else escape_text(p) for p in parts if p != ""))


def container(classes, body):
    """`body` in a container with `classes`, which outputs style"""
    return Rst(f".. container:: {classes}\n\n{indent(Rst(body), 3, first=True)}\n")


def cell(item):
    """A table cell: maps become nested tables, everything else code"""
    if isinstance(item, dict):
        return mapping(item)
    return literal(written(item))


def mapping(data, caption=None):
    """A two-column table of a map's keys and values"""
    return table(["Name", "Value"],
                 [[escape_text(written(key).lstrip(":")), item] for key, item in data.items()],
                 caption, header=False)


def table(headers, rows, caption=None, header=True):
    """A list-table with a header row (unless not `header`); cells are
    rst, or values written with `cell`"""
    lines = [f".. list-table:: {escape_text(caption) if caption else ''}".rstrip()]
    if header:
        lines.append("   :header-rows: 1")
    lines.append("")
    for row in ([headers] if header else []) + [list(r) for r in rows]:
        for n, item in enumerate(row):
            value = item if isinstance(item, Rst) else (
                escape_text(item) if row is headers else cell(item))
            lines.append(f"   {'* -' if n == 0 else '  -'} {indent(value, 7)}".rstrip())
    return Rst("\n".join(lines) + "\n")
