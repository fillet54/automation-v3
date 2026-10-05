"""HTML helpers for blocks and forms that render themselves"""

from html import escape

from . import edn

TABLE = "my-1 text-sm border-collapse"
HEAD = "px-3 py-1 text-left font-semibold text-gray-700 bg-gray-50 border"
CELL = "px-3 py-1 align-top border"


def text(value):
    """A value as readable, escaped text: keywords and literals as edn"""
    if isinstance(value, str) and not isinstance(value, edn.Symbol):
        return escape(value)
    return escape(edn.writes(value).strip())


def value(item):
    """A cell's content: maps become nested tables, everything else text"""
    if isinstance(item, dict):
        return mapping(item)
    return f'<span class="font-mono text-xs">{text(item)}</span>'


def mapping(data, caption=None):
    """A two-column table of a map's keys and values"""
    rows = "".join(
        f'<tr><th class="{HEAD}">{escape(str(key).lstrip(":"))}</th>'
        f'<td class="{CELL}">{value(item)}</td></tr>'
        for key, item in data.items()
    )
    return _table(rows, caption)


def table(headers, rows, caption=None):
    """A table with a header row; cells are rendered with `value`"""
    head = "".join(f'<th class="{HEAD}">{escape(h)}</th>' for h in headers)
    body = "".join(
        "<tr>" + "".join(f'<td class="{CELL}">{value(c)}</td>' for c in row) + "</tr>"
        for row in rows
    )
    return _table(f"<tr>{head}</tr>{body}", caption)


def _table(rows, caption):
    caption = (
        f'<caption class="text-left text-xs text-gray-500">{escape(caption)}</caption>'
        if caption else ""
    )
    # Inline width: prose styles would otherwise stretch tables full width
    return f'<table class="{TABLE}" style="width: auto">{caption}{rows}</table>'
