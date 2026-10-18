"""reStructuredText helpers for blocks and forms that render themselves

Blocks write rst (see BuildingBlock.as_rst), so a step reads the same on a
page, in a static site and in a PDF. These helpers escape values, so a
value never turns into markup, and write the constructs blocks use most.
"""

from ..documents.template import Rst, indent
from ..documents.template import literal as _literal
from ..documents.template import text as _text
from . import edn


def written(value):
    """A value as written in a script: strings as they are, everything
    else (keywords, symbols, numbers, collections) as edn"""
    if isinstance(value, str) and not isinstance(value, (edn.Symbol, edn.Keyword)):
        return value
    return edn.writes(value)


def text(value):
    """A value as plain text"""
    return _text(written(value))


def code(*values):
    """Values as inline code, separated by spaces"""
    return _literal(" ".join(edn.writes(v) for v in values))


def strong(value):
    value = _text(value)
    return Rst(f"**{value}**") if value else value


def line(*parts):
    """Parts (rst, or text to escape) joined by spaces into one line"""
    return Rst(" ".join(p if isinstance(p, Rst) else _text(p) for p in parts if p != ""))


def container(classes, body):
    """`body` in a container with `classes`, which outputs style"""
    return Rst(f".. container:: {classes}\n\n{indent(Rst(body), 3, first=True)}\n")


def cell(item):
    """A table cell: maps become nested tables, everything else code"""
    if isinstance(item, dict):
        return mapping(item)
    return _literal(written(item))


def mapping(data, caption=None):
    """A two-column table of a map's keys and values"""
    return table(["Name", "Value"],
                 [[_text(written(key).lstrip(":")), item] for key, item in data.items()],
                 caption, header=False)


def table(headers, rows, caption=None, header=True):
    """A list-table with a header row (unless not `header`); cells are
    rst, or values written with `cell`"""
    lines = [f".. list-table:: {_text(caption) if caption else ''}".rstrip()]
    if header:
        lines.append("   :header-rows: 1")
    lines.append("")
    for row in ([headers] if header else []) + [list(r) for r in rows]:
        for n, item in enumerate(row):
            value = item if isinstance(item, Rst) else (
                _text(item) if row is headers else cell(item))
            lines.append(f"   {'* -' if n == 0 else '  -'} {indent(value, 7)}".rstrip())
    return Rst("\n".join(lines) + "\n")
