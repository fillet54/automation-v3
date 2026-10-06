"""Small additions for these docs

- :status:`passed` shows a run outcome the way the web UI badges it.
"""

from docutils import nodes

STATUSES = {"passed", "failed", "error", "partial", "blocked", "running", "queued",
            "skipped", "not identical"}


def status_role(name, rawtext, text, lineno, inliner, options=None, content=()):
    word = text.strip().lower()
    if word not in STATUSES:
        message = inliner.reporter.error(f"unknown status {text!r}", line=lineno)
        return [inliner.problematic(rawtext, rawtext, message)], [message]
    css = "ui-status-word ui-status-word--" + word.replace(" ", "-")
    return [nodes.inline(rawtext, word, classes=css.split())], []


def setup(app):
    app.add_role("status", status_role)
    return {"parallel_read_safe": True, "parallel_write_safe": True}
