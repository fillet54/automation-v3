"""Mermaid diagrams, drawn in the web UI's look

``.. mermaid::`` holds a Mermaid diagram (https://mermaid.js.org); the page
draws it in the browser with the ELK layout, in the site's colours, fonts and
light or dark theme (static/diagrams.js). Options:

``:caption:``
   A line under the diagram, also its accessible name.
``:name:``
   A target to reference it by.

Nodes take the site's tones as classes (``A[Server]:::accent``): accent,
success, danger, warning, info, review and ghost (something outside the
system, drawn dashed).

Mermaid and the ELK layout are vendored in static/mermaid, so diagrams draw
on a closed network, and only pages with a diagram load them. Without
JavaScript, or until it has drawn, a diagram shows as its source.
"""

from pathlib import Path

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.util.docutils import SphinxDirective
from sphinx.util.fileutil import copy_asset

STATIC = Path(__file__).resolve().parent / "static"


class mermaid(nodes.General, nodes.Element):
    pass


class Mermaid(SphinxDirective):
    has_content = True
    option_spec = {"caption": directives.unchanged, "name": directives.unchanged}

    def run(self):
        source = "\n".join(self.content).strip()
        if not source:
            raise self.error("A mermaid diagram needs its source as the directive's content")
        node = mermaid(source=source, caption=self.options.get("caption", ""))
        self.set_source_info(node)
        self.add_name(node)
        return [node]


def visit_html(self, node):
    caption = node["caption"]
    ids = f' id="{node["ids"][0]}"' if node["ids"] else ""
    label = f' aria-label="{self.encode(caption)}"' if caption else ""
    self.body.append(
        f'<figure class="ui-diagram"{ids}>'
        f'<div class="ui-diagram__canvas" data-diagram role="img"{label}>'
        f'<pre class="ui-diagram__source">{self.encode(node["source"])}</pre></div>')
    if caption:
        self.body.append(f"<figcaption>{self.encode(caption)}</figcaption>")
    self.body.append("</figure>")
    raise nodes.SkipNode


def visit_other(self, node):
    raise nodes.SkipNode


def add_scripts(app, pagename, templatename, context, doctree):
    """Mermaid only on the pages that draw a diagram"""
    if doctree is not None and doctree.next_node(mermaid) is not None:
        app.add_js_file("mermaid/mermaid.min.js", loading_method="defer")
        app.add_js_file("diagrams.js", loading_method="defer")


def copy_static(app, exception):
    if exception is None and app.builder.format == "html":
        copy_asset(str(STATIC), str(Path(app.outdir) / "_static"))


def setup(app):
    app.add_node(mermaid, html=(visit_html, None), latex=(visit_other, None),
                 text=(visit_other, None), man=(visit_other, None), texinfo=(visit_other, None))
    app.add_directive("mermaid", Mermaid)
    app.connect("html-page-context", add_scripts)
    app.connect("build-finished", copy_static)
    return {"parallel_read_safe": True, "parallel_write_safe": True}
