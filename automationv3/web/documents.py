"""Documents on the app's pages: links to its pages, its outcome badges,
and caches, around documents/ (which knows nothing of Flask)"""

import functools
from collections import OrderedDict

from flask import get_template_attribute, url_for

from ..documents import core, html, script
from ..documents.template import Snippets
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

    def source(self, run, path, line, col=0):
        return edit_url(run, path, line, col)


def edit_url(run, path=None, line=None, col=0):
    """The editor at file `path` (the run's script by default) of a scratch
    run's workspace, at `line` (1-based) and `col`, with the run to go
    back to; None for a run that isn't scratch or whose workspace isn't
    here, or a file that isn't in it"""
    from ..services.scratch import SCRATCH, UPLOADED
    from .context import workspace_root
    workspace = run.get("workspace")
    if run.get("report_id") != SCRATCH or not workspace or run.get("source") == UPLOADED:
        return None
    found = workspace_root(workspace)
    path = path or run.get("script")
    if found is None or not path or not (found / path).is_file():
        return None
    return url_for("workspace.index", id=workspace, path=path, line=line or None,
                   col=col or None if line else None, run=run["id"])


def failure_place(run, events):
    """(path, line, col) of where a run's first failing step failed: in
    the script itself if its trace goes through it, else where the trace
    starts; the step's own line if it has no trace. None if no step
    failed."""
    from ..framework import excerpt, source
    from ..framework.paths import posix
    ended = next((e for e in events if e["kind"] == "step_end" and not e.get("passed")), None)
    if ended is None:
        return None
    spans = [excerpt._as_span(s) for s in excerpt.frames(ended.get("trace"))]
    spans = [s for s in spans if s.source]
    script = posix(run.get("script") or "")
    mine = [s for s in spans if posix(s.source) == script]
    if mine or spans:
        span = (mine or spans)[0]
        return posix(span.source), span.line, span.col
    if ended.get("index") is None:
        return None
    try:  # the statement the event counts, in the script as it is now
        found = source.statements(source.parse(edit_text(run)))[ended["index"]]
    except Exception:
        return None
    return script, found.span.line, found.span.col


def edit_text(run):
    from .context import workspace_root
    return (workspace_root(run["workspace"]) / run["script"]).read_text(encoding="utf-8")


class LiveHooks(html.Hooks):
    """The app's outcome badges and chevrons in documents; with `poll`
    (node -> URL or None), data blocks that may change refresh themselves"""

    def __init__(self, poll=None):
        self.outcome = get_template_attribute("ui/outcomes.html", "outcome")
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
    from .app import requirement_key, requirement_lookup
    ready()
    key = (report_id, run["id"], run.get("outcome"), requirement_key())
    if run.get("outcome") is not None and key in _finished:
        _finished.move_to_end(key)
        return _finished[key]
    data = ReportData(root, report_id, status=status, links=LiveLinks())
    variation = (run.get("variation") or {}).get("name")
    tree = script.parsed(data.script_text(run), variation, results=True, variations=False)
    context = core.Context(data=data, run=run, snippets=Snippets(snippets),
                           requirement_lookup=requirement_lookup)
    found = render(core.resolved(tree, context))
    if run.get("outcome") is not None:
        _finished[key] = found
        while len(_finished) > FINISHED_CACHE:
            _finished.popitem(last=False)
    return found


def script_document(text, variation=None, diagnostics=(), variations=True):
    """The HTML of a script's document, before any run"""
    from .app import requirement_lookup
    ready()
    tree = script.parsed(text, variation, results=False, diagnostics=diagnostics,
                         variations=variations)
    return render(core.resolved(tree, core.Context(requirement_lookup=requirement_lookup)))


def rst_document(text):
    """The HTML of a plain reStructuredText file"""
    from .app import requirement_lookup
    return render(core.resolved(core.parse(text),
                                core.Context(requirement_lookup=requirement_lookup)))


# A report's document

@functools.lru_cache(maxsize=64)
def parsed_report(text):
    return core.parse(text, source_path="report.rst")


def report_context(root, report_id, status=None, data=None, **extra):
    from .app import requirement_lookup
    from ..services.reports import export
    return export.context(root, report_id, host=core.LIVE, links=LiveLinks(),
                          status=status, data=data,
                          requirement_lookup=requirement_lookup, extra=extra)


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
