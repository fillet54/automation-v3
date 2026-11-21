"""The Sphinx extension specs are built with (see render.py)

It gives the ``requirement`` directive its look on a spec's page: the id,
its attributes and the requirements it satisfies over the text. Links to
requirement pages are written as ``@req/ID``; the server makes them real
links, in the context the page is shown in. When the build finishes it
writes nav.json, the spec's table of contents, for the page's side column.
The builder is dirhtml, with a theme (theme/) whose page is JSON.

This module must not import the rest of automationv3: Sphinx registers
directives globally, and the importer's own ``requirement`` directive
must not meet this one.
"""

import json
from html import escape
from pathlib import Path

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.util.docutils import SphinxDirective

from ....framework.source import AnyOption


def req_link(id):
    return f'<a class="spec-req__link" href="@req/{escape(id)}">{escape(id)}</a>'


class RequirementDirective(SphinxDirective):
    required_arguments = 1
    has_content = True
    option_spec = AnyOption(satisfies=directives.unchanged)

    def run(self):
        id = self.arguments[0].strip()
        reqs = getattr(self.env, "spec_requirements", None)
        if reqs is None:
            reqs = self.env.spec_requirements = {}
        reqs.setdefault(self.env.docname, []).append(id)
        options = {k: " ".join((v or "").split()) for k, v in self.options.items()}
        satisfies = [s.strip() for s in options.pop("satisfies", "").split(",") if s.strip()]
        head = [f'<div class="spec-req__head" id="{escape(id)}">',
                f'<a class="spec-req__id" href="@req/{escape(id)}">{escape(id)}</a>']
        for name, value in sorted(options.items()):
            head.append(f'<span class="spec-req__attr"><span>{escape(name)}</span> '
                        f'{escape(value)}</span>')
        if satisfies:
            head.append('<span class="spec-req__satisfies">satisfies '
                        + ", ".join(req_link(s) for s in satisfies) + "</span>")
        head.append("</div>")
        box = nodes.container(classes=["spec-req"])
        box += nodes.raw("", "".join(head), format="html")
        text = nodes.container(classes=["spec-req__text"])
        self.state.nested_parse(self.content, self.content_offset, text)
        box += text
        return [box]


def purge_requirements(app, env, docname):
    reqs = getattr(env, "spec_requirements", None)
    if reqs is not None:
        reqs.pop(docname, None)


def merge_requirements(app, env, docnames, other):
    other_reqs = getattr(other, "spec_requirements", None)
    if not other_reqs:
        return
    reqs = getattr(env, "spec_requirements", None)
    if reqs is None:
        reqs = env.spec_requirements = {}
    for docname in docnames:
        if docname in other_reqs:
            reqs[docname] = list(other_reqs[docname])


def write_nav(app, exception):
    """nav.json: {"doc", "title", "children": [...]} from the root document
    down, and "requirements": requirement id -> the document it is in"""
    if exception:
        return
    env = app.env

    def entry(doc, seen):
        seen = seen | {doc}
        return {"doc": doc, "title": env.titles[doc].astext() if doc in env.titles else doc,
                "children": [entry(child, seen) for child in env.toctree_includes.get(doc, [])
                             if child not in seen and child in env.all_docs]}

    nav = entry(app.config.root_doc, set())
    by_doc = getattr(env, "spec_requirements", None) or {}
    found = {}
    for doc in env.all_docs:
        for id in by_doc.get(doc, ()):
            found.setdefault(id, doc)
    nav["requirements"] = found
    Path(app.outdir, "nav.json").write_text(json.dumps(nav))


def setup(app):
    app.add_directive("requirement", RequirementDirective, override=True)
    app.connect("env-purge-doc", purge_requirements)
    app.connect("env-merge-info", merge_requirements)
    app.connect("build-finished", write_nav)
    return {"parallel_read_safe": True, "version": "1"}
