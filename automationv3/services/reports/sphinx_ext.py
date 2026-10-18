"""The report's documents as a Sphinx project: a static site and a PDF

A frozen report builds with Sphinx (see services/reports/build.py): its
report.rst is the root document, each run a page of its own (its script,
with what came of each step), and the directives are the same ones live
pages resolve, resolved while Sphinx reads, from the report folder:

    automation_root, automation_folder   where the report folder is
    automation_server_url                 the server, for requirement links
    automation_exported, automation_manifest_hash
    automation_snippets                   the report template's snippets/
    automation_latex                      values for latex.tex_t (automation.*)

Links a directive writes to a run or an attached file are rewritten for
the output: a relative link in the site, plain text in the PDF.
"""

import shutil
from pathlib import Path

from docutils import nodes
from docutils.parsers.rst import Directive, directives
from docutils.statemachine import StringList

from ...documents import core, script
from ...documents.template import Snippets

RUN, FILE = "automation-run:", "automation-file:"


class SiteLinks:
    """Links written while a build reads: markers, rewritten per output
    once Sphinx knows where each page goes"""

    def __init__(self, server_url=""):
        self.base = (server_url or "").rstrip("/")

    def run(self, report_id, run_id):
        return f"{RUN}{run_id}"

    def file(self, report_id, run_id, name):
        return f"{FILE}{run_id}/{name}"

    def requirement(self, id, snapshot):
        from .export import ServerLinks
        return ServerLinks(self.base).requirement(id, snapshot)


_contexts = {}


def build_context(env):
    """The Context a build's documents resolve with: one per build, and
    the run a run page is about (see context_of)"""
    found = _contexts.get(id(env.app))
    if found is None:
        from .data import ReportData
        config = env.config
        data = ReportData(config.automation_root, config.automation_folder,
                          links=SiteLinks(config.automation_server_url))
        from ...framework import rst
        from ...framework.requirement import Requirement
        snapshots = data.snapshots
        rst.set_requirement_lookup(  # scripts' :req: quote the text the report kept
            lambda id: Requirement(id, (snapshots.get(id) or {}).get("text")))
        found = _contexts[id(env.app)] = core.Context(
            data=data, host=core.EXPORT,
            snippets=Snippets([config.automation_snippets]),
            exported=config.automation_exported,
            manifest_hash=config.automation_manifest_hash)
    return found


def run_context(context, run_id):
    run = context.data.run(run_id)
    return core.Context(data=context.data, run=run, snippets=context.snippets,
                        host=context.host, exported=context.exported,
                        manifest_hash=context.manifest_hash)


class RunDocument(Directive):
    """``.. run-document:: RUN``: the run's script, as it ran, with what
    came of each step, read in place (its titles become the page's)"""

    required_arguments = 1

    def run(self):
        document = self.state.document
        context = build_context(document.settings.env)
        run = context.data.run(self.arguments[0])
        if run is None:
            raise self.error(f"no run {self.arguments[0]} in the report")
        document["automation_run"] = run["id"]
        variation = (run.get("variation") or {}).get("name")
        rst = script.source(context.data.statements(run), variation, results=True,
                            variations=False)
        self.state_machine.insert_input(
            StringList(rst.splitlines(), f"{run['script']} (run {run['id']})"),
            run["script"])
        return []


def rewrite_links(app, doctree, docname):
    """Run and file links: relative in the site, plain text in the PDF"""
    html = app.builder.format == "html"
    for node in list(doctree.findall(nodes.reference)):
        uri = node.get("refuri", "")
        if not uri.startswith((RUN, FILE)):
            continue
        if not html:
            node.replace_self(nodes.inline("", "", *node.children))
        elif uri.startswith(RUN):
            node["refuri"] = app.builder.get_relative_uri(docname, f"runs/{uri[len(RUN):]}")
        else:
            depth = docname.count("/")
            node["refuri"] = "../" * depth + "_files/" + uri[len(FILE):]


def copy_files(app, exception):
    """Every run's attached files, into the site's _files/RUN/"""
    if exception is not None or app.builder.format != "html":
        return
    context = build_context(app.env)
    for run in context.data.runs:
        for name in context.data.files(run):
            target = Path(app.outdir) / "_files" / run["id"] / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(context.data.file_path(run, name), target)


def latex_values(app):
    """The automation.* values latex.tex_t reads"""
    if app.builder.format == "latex":
        app.builder.context["automation"] = app.config.automation_latex


def document_context(document):
    """The Context of a document a build reads (see core.build_contexts)"""
    env = getattr(document.settings, "env", None)
    if env is None or "automation_root" not in env.config:
        return None
    context = build_context(env)
    run = document.get("automation_run")
    return run_context(context, run) if run else context


def setup(app):
    from ...framework.plugins import load_plugins
    load_plugins()  # their directives, roles, filters and snippets
    if document_context not in core.build_contexts:
        core.build_contexts.append(document_context)
    for name in ("root", "folder", "server_url", "exported", "manifest_hash", "snippets"):
        app.add_config_value(f"automation_{name}", "", "env")
    app.add_config_value("automation_latex", {}, "env")
    directives.register_directive("run-document", RunDocument)
    app.connect("builder-inited", latex_values)
    app.connect("doctree-resolved", rewrite_links)
    app.connect("build-finished", copy_files)
    return {"parallel_read_safe": False, "parallel_write_safe": True}
