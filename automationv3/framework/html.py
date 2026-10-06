"""HTML helpers for blocks and forms that render themselves"""

from html import escape

from . import edn

# Classes from the web UI's stylesheet (web/static/css/ui.css)
TABLE = "ui-datatable"


def text(value):
    """A value as readable, escaped text: keywords and literals as edn"""
    if isinstance(value, str) and not isinstance(value, edn.Symbol):
        return escape(value)
    return escape(edn.writes(value).strip())


def value(item):
    """A cell's content: maps become nested tables, everything else text"""
    if isinstance(item, dict):
        return mapping(item)
    return f'<span class="ui-mono">{text(item)}</span>'


def mapping(data, caption=None):
    """A two-column table of a map's keys and values"""
    rows = "".join(
        f'<tr><th>{escape(str(key).lstrip(":"))}</th>'
        f'<td>{value(item)}</td></tr>'
        for key, item in data.items()
    )
    return _table(rows, caption)


def table(headers, rows, caption=None):
    """A table with a header row; cells are rendered with `value`"""
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{value(c)}</td>" for c in row) + "</tr>"
        for row in rows
    )
    return _table(f"<tr>{head}</tr>{body}", caption)


def _table(rows, caption):
    caption = f"<caption>{escape(caption)}</caption>" if caption else ""
    return f'<table class="{TABLE}">{caption}{rows}</table>'
