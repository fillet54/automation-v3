"""Sphinx extension: ``extensions = ["mermaid_diag.sphinx"]``.

Diagrams are rendered while the documents are read (so a broken one is a warning with its file and line), kept
in a cache under the doctree directory, and written as inline SVG in HTML and as a picture in LaTeX. See
mermaid_diag.docutils for the directive.

conf.py settings:

``mermaid_diag_config``           Mermaid config merged over the defaults (dict).
``mermaid_diag_dark``             Follow dark mode too (default True).
``mermaid_diag_theme_attribute``  The root element attribute a theme switcher sets: ``<html data-theme="dark">``
                                  (default "data-theme"; automation-v3 uses "data-ui-theme").
``mermaid_diag_engine``           "auto" (default), "node" or "quickjs".
``mermaid_diag_timeout``          Seconds one diagram may take (default 600).
``mermaid_diag_fonts``            Ship the IBM Plex fonts with the HTML (default True). False when the site
                                  already loads them.
``mermaid_diag_latex_scale``      Resolution of the LaTeX pictures, as a multiple of the diagram's size (default 3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docutils import nodes
from sphinx.application import Sphinx
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective

from . import __version__
from .docutils import MermaidDirective, Settings, html_markup, mermaid_diagram

logger = logging.getLogger(__name__)
STATIC_DIR = "mermaid-diag"


class SphinxMermaidDirective(SphinxDirective, MermaidDirective):
    def settings(self) -> Settings:
        c = self.config
        return Settings(
            config=dict(c.mermaid_diag_config or {}),
            dark=bool(c.mermaid_diag_dark),
            theme_attribute=c.mermaid_diag_theme_attribute,
            engine=c.mermaid_diag_engine,
            timeout=c.mermaid_diag_timeout,
            cache_dir=str(Path(self.env.doctreedir) / "mermaid-diag"),
        )

    def source_path(self, argument: str) -> tuple[Path, str]:
        rel, abs_ = self.env.relfn2path(argument, self.env.docname)
        return Path(abs_), rel

    def note_dependency(self, path: str) -> None:
        self.env.note_dependency(path)

    def report(self, message: str) -> None:
        logger.warning("the mermaid diagram couldn't be rendered: %s", message,
                       location=(self.env.docname, self.lineno), type="mermaid", subtype="render")


def visit_html(self, node: mermaid_diagram) -> None:
    used = self.__dict__.setdefault("_mermaid_diag_ids", set())
    self.body.append(html_markup(node, used))
    raise nodes.SkipNode


def visit_latex(self, node: mermaid_diagram) -> None:
    if "error" in node:
        self.body.append(r"\begin{sphinxVerbatim}" + "\n" + node["source"] + "\n" + r"\end{sphinxVerbatim}" + "\n")
        raise nodes.SkipNode
    builder = self.builder
    name = f"{node['svg_id']}.png"
    target = Path(builder.outdir) / name
    try:
        if not target.exists():
            from . import cjk
            from .api import picture_svg
            from .raster import to_png
            svg = node["light"]
            if cjk.needs_fallback(node["source"]):
                svg = picture_svg(node["source"], "light", config=node.get("config"), svg_id=node["svg_id"],
                                  engine=builder.config.mermaid_diag_engine)
            target.write_bytes(to_png(svg, scale=builder.config.mermaid_diag_latex_scale))
    except Exception as e:  # noqa: BLE001 -- no novasvg, or a picture too large
        logger.warning("mermaid diagram %s: no picture for LaTeX (%s); writing its source", node["svg_id"], e,
                       location=node, type="mermaid", subtype="latex")
        self.body.append(r"\begin{sphinxVerbatim}" + "\n" + node["source"] + "\n" + r"\end{sphinxVerbatim}" + "\n")
        raise nodes.SkipNode
    width, _ = _size(node["light"])
    # The diagram's CSS size (96 px to the inch); \sphinxincludegraphics shrinks it to the line when wider.
    self.body.append(r"\sphinxincludegraphics[width=%.2fbp]{%s}" % (width * 0.75, name) + "\n")
    raise nodes.SkipNode


def _size(svg: str) -> tuple[float, float]:
    from .api import _VIEWBOX
    m = _VIEWBOX.search(svg)
    return (float(m[3]), float(m[4])) if m else (400.0, 300.0)


def visit_text(self, node: mermaid_diagram) -> None:
    self.add_text("[diagram]")  # the figure's caption, if any, follows
    raise nodes.SkipNode


def visit_source(self, node: mermaid_diagram) -> None:
    self.visit_literal_block(nodes.literal_block(node["source"], node["source"]))
    raise nodes.SkipNode


def depart(self, node: mermaid_diagram) -> None:
    pass


def add_css(app: Sphinx, pagename: str, templatename: str, context: dict, doctree: Any) -> None:
    """The stylesheet only on pages that have a diagram."""
    if doctree is not None and doctree.next_node(mermaid_diagram) is not None:
        app.add_css_file(f"{STATIC_DIR}/mermaid-diag.css")


def copy_static(app: Sphinx, exception: Exception | None) -> None:
    if exception is not None or app.builder.format != "html":
        return
    from .assets import copy_static as copy, figure_css
    dest = Path(app.outdir) / "_static" / STATIC_DIR
    if app.config.mermaid_diag_fonts:
        copy(dest)
    else:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "mermaid-diag.css").write_text(figure_css(), encoding="utf-8")


def setup(app: Sphinx) -> dict[str, Any]:
    app.add_config_value("mermaid_diag_config", {}, "env", [dict])
    app.add_config_value("mermaid_diag_dark", True, "env", [bool])
    app.add_config_value("mermaid_diag_theme_attribute", "data-theme", "env", [str])
    app.add_config_value("mermaid_diag_engine", None, "", [str, type(None)])
    app.add_config_value("mermaid_diag_timeout", None, "", [float, int, type(None)])
    app.add_config_value("mermaid_diag_fonts", True, "html", [bool])
    app.add_config_value("mermaid_diag_latex_scale", 3.0, "", [float, int])
    app.add_node(
        mermaid_diagram,
        html=(visit_html, depart),
        latex=(visit_latex, depart),
        text=(visit_text, depart),
        man=(visit_source, depart),
        texinfo=(visit_source, depart),
    )
    app.add_directive("mermaid", SphinxMermaidDirective, override=True)
    app.connect("html-page-context", add_css)
    app.connect("build-finished", copy_static)
    return {"version": __version__, "parallel_read_safe": True, "parallel_write_safe": True}
