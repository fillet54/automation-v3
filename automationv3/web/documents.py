"""Documents on the app's pages: links to its pages, its outcome badges,
and caches, around documents/ (which knows nothing of Flask)"""

import functools
from collections import OrderedDict

from flask import get_template_attribute, url_for

from ..documents import core, html, script
from ..documents.template import Snippets
from ..framework import rst as script_rst
from ..services.reports.data import Links, ReportData


class LiveLinks(Links):
    """Links to the app's own pages"""

    def run(self, report_id, run_id):
        return url_for("reports.run", report_id=report_id, run_id=run_id)

    def requirement(self, id, snapshot):
        context = (snapshot or {}).get("context")
        return url_for("requirements.requirement", id=id,
                       **({"context": context} if context else {}))

    def file(self, report_id, run_id, name):
        return url_for("reports.run_file", report_id=report_id, run_id=run_id, name=name)


class LiveHooks(html.Hooks):
    """The app's outcome badges and chevrons in documents; with `poll`
    (node -> URL or None), data blocks that may change refresh themselves"""

    def __init__(self, poll=None):
        self.outcome = get_template_attribute("ui/components.html", "outcome")
        self.icon = get_template_attribute("ui/components.html", "icon")
        self.poll = poll

    def block_attributes(self, node):
        url = self.poll(node) if self.poll else None
        if not url:
            return ""
        return (f' hx-get="{url}" hx-trigger="every 3s" hx-swap="outerHTML"'
                ' hx-select="unset"')

    def verdict(self, state):
        return str(self.outcome(state))

    def summary_icon(self):
        return str(self.icon("chevron-right", 12))


def render(document, hooks=None):
    return html.render(document, hooks or LiveHooks())


def ready():
    """Plugins loaded: their directives, roles and snippets registered"""
    from ..framework.plugins import load_plugins
    load_plugins()


# A finished run's page never changes (until it is rerun, as a new run):
# keep its HTML
_finished = OrderedDict()
FINISHED_CACHE = 200


def run_document(root, report_id, run, status, snippets=()):
    """The HTML of a run's document: its script, each step with its result"""
    ready()
    key = (report_id, run["id"], run.get("outcome"), script_rst.requirement_key())
    if run.get("outcome") is not None and key in _finished:
        _finished.move_to_end(key)
        return _finished[key]
    data = ReportData(root, report_id, status=status, links=LiveLinks())
    variation = (run.get("variation") or {}).get("name")
    tree = script.parsed(data.script_text(run), variation, results=True, variations=False)
    context = core.Context(data=data, run=run, snippets=Snippets(snippets))
    found = render(core.resolved(tree, context))
    if run.get("outcome") is not None:
        _finished[key] = found
        while len(_finished) > FINISHED_CACHE:
            _finished.popitem(last=False)
    return found


def script_document(text, variation=None, diagnostics=(), variations=True):
    """The HTML of a script's document, before any run"""
    ready()
    tree = script.parsed(text, variation, results=False, diagnostics=diagnostics,
                         variations=variations)
    return render(core.resolved(tree, core.Context()))


def rst_document(text):
    """The HTML of a plain reStructuredText file"""
    return render(core.resolved(core.parse(text), core.Context()))


# A report's document

@functools.lru_cache(maxsize=64)
def _parsed_report(text, requirement_key):
    return core.parse(text, source_path="report.rst")


def parsed_report(text):
    return _parsed_report(text, script_rst.requirement_key())


def report_context(root, report_id, status, **extra):
    from ..services.reports import export
    return export.context(root, report_id, host=core.LIVE, links=LiveLinks(),
                          status=status, extra=extra)


def report_document(text, context, poll=None):
    """The HTML of a report's document `text`, and its problems: each
    data block refreshes itself (from `poll(node)`) while it may change"""
    from ..services.reports import export
    ready()
    document = core.resolved(parsed_report(text), context)
    return render(document, LiveHooks(poll)), export.problems(document)


def report_block(text, serial, context, poll=None):
    """The HTML of one data block of a report's document, or None"""
    document = core.resolved_block(parsed_report(text), serial, context)
    return render(document, LiveHooks(poll)) if document is not None else None
