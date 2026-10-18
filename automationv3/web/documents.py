"""Documents on the app's pages: links to its pages, its outcome badges,
and caches, around documents/ (which knows nothing of Flask)"""

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
    """The app's outcome badges and chevrons in documents"""

    def __init__(self):
        self.outcome = get_template_attribute("ui/components.html", "outcome")
        self.icon = get_template_attribute("ui/components.html", "icon")

    def verdict(self, state):
        return str(self.outcome(state))

    def summary_icon(self):
        return str(self.icon("chevron-right", 12))


def render(document):
    return html.render(document, LiveHooks())


# A finished run's page never changes (until it is rerun, as a new run):
# keep its HTML
_finished = OrderedDict()
FINISHED_CACHE = 200


def run_document(root, report_id, run, status, snippets=()):
    """The HTML of a run's document: its script, each step with its result"""
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
    tree = script.parsed(text, variation, results=False, diagnostics=diagnostics,
                         variations=variations)
    return render(core.resolved(tree, core.Context()))


def rst_document(text):
    """The HTML of a plain reStructuredText file"""
    return render(core.resolved(core.parse(text), core.Context()))
