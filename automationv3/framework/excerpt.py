"""Source excerpts: the lines a span covers, marked, for error reports

A failure or a diagnostic says where it happened as edn.Spans (or their
dicts, as stored in a run's events). `excerpt` turns one into the lines
of the file it points into, with the columns it covers marked, so a page
can show the code with a caret line under the offending form. `frames`
picks the spans of a trace worth showing.
"""


def _get(span, key):
    return span[key] if isinstance(span, dict) else getattr(span, key)


def location(span):
    """path:line:col (1-based column) of a span"""
    return f"{_get(span, 'source')}:{_get(span, 'line')}:{_get(span, 'col') + 1}"


def excerpt(files, span, context=1):
    """The lines of `span` in `files` (path -> text), with `context` lines
    before it: {"where", "path", "line", "rows": [{"no", "text", "mark"}]},
    where a row's mark is (start col, end col) for the part of the line
    the span covers, or None. None if the span's file isn't in `files`."""
    if span is None:
        return None
    path = _get(span, "source")
    text = files.get(path) if path is not None else None
    if text is None:
        return None
    lines = text.splitlines()
    line, col = _get(span, "line"), _get(span, "col")
    end_line, end_col = _get(span, "end_line"), _get(span, "end_col")
    if not 1 <= line <= len(lines):
        return None
    end_line = min(end_line, len(lines))
    rows = []
    for no in range(max(1, line - context), end_line + 1):
        source = lines[no - 1]
        mark = None
        if line <= no <= end_line:
            indent = len(source) - len(source.lstrip())
            start = col if no == line else indent
            end = end_col if no == end_line else len(source.rstrip())
            if end > start:
                mark = (start, end)
        if rows or mark or source.strip():  # no blank lines leading in
            rows.append({"no": no, "text": source, "mark": mark})
    # Dedent the excerpt as a whole: rvt content is indented in the file
    indents = [len(r["text"]) - len(r["text"].lstrip()) for r in rows if r["text"].strip()]
    cut = min(indents) if indents else 0
    for row in rows:
        row["text"] = row["text"][cut:]
        if row["mark"]:
            row["before"] = row["text"][:row["mark"][0] - cut]
            row["marked"] = row["text"][row["mark"][0] - cut:row["mark"][1] - cut]
            row["after"] = row["text"][row["mark"][1] - cut:]
    return {"where": location(span), "path": path, "line": line, "rows": rows}


def _contains(outer, inner):
    if _get(outer, "source") != _get(inner, "source"):
        return False
    start = (_get(outer, "line"), _get(outer, "col"))
    end = (_get(outer, "end_line"), _get(outer, "end_col"))
    return start <= (_get(inner, "line"), _get(inner, "col")) and \
        (_get(inner, "end_line"), _get(inner, "end_col")) <= end


def frames(trace):
    """The spans of a trace (innermost first) worth showing: where it
    happened, then each call that led there. Forms that merely enclose
    the one before them are left out."""
    shown = []
    for span in trace or []:
        if shown and _contains(span, shown[-1]):
            continue
        shown.append(span)
    return shown


def failure_view(files, message, trace, traceback=""):
    """What a page shows for a failure: its message, an excerpt for where
    it happened and for each call that led there, and the traceback (if
    there is one) to show on request"""
    excerpts = []
    for span in frames(trace):
        found = excerpt(files, span)
        if found is not None:
            excerpts.append(found)
    return {
        "message": message,
        "excerpts": excerpts,
        "traceback": traceback if "Traceback (most recent call last)" in (traceback or "")
        else "",
    }
