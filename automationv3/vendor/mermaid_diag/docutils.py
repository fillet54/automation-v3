"""The ``.. mermaid::`` directive, for docutils and (through mermaid_diag.sphinx) Sphinx.

    .. mermaid::
       :caption: How a request flows
       :name: request-flow

       flowchart LR
         user([User]):::ghost --> api[API]:::accent --> db[(Postgres)]

    .. mermaid:: diagrams/deploy.mmd

The source is the directive's content, or a file named by its argument (relative to the document). Options:

``:caption:``  A caption under the diagram (also its accessible name). Numbered like any figure in Sphinx.
``:name:``     A target to reference it by.
``:alt:``      The accessible name, when it isn't the caption.
``:align:``    left, center (default) or right.
``:width:``    The widest it may be drawn (a CSS length: ``600px``, ``80%``); by default its natural size.
``:scroll:``   Keep the natural size and scroll sideways when the page is narrower, instead of shrinking it.
``:layout:``   elk (default), dagre, or another layout Mermaid knows.
``:config:``   Mermaid config as JSON, merged over the defaults: ``{"flowchart": {"curve": "linear"}}``.
``:class:``    More classes for the figure.

Nodes take the palette's tones as classes: ``A[Server]:::accent`` (accent, success, danger, warning, info,
review, verify, and ghost for something outside the system).

Plain docutils: call ``register()`` once before publishing; the first diagram of each HTML page brings the
stylesheet and fonts (embedded, unless ``register(css_url=...)`` names a stylesheet to link instead, see
mermaid_diag.assets.copy_static).
"""

from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from docutils import nodes
from docutils.parsers.rst import Directive, directives

from .api import RenderError, diagram_id, render


class mermaid_diagram(nodes.General, nodes.Element):
    """A rendered diagram: ``svg`` (inline, themed), ``light`` (for pictures), ``source``, ``svg_id``, ``alt``,
    ``width``, ``error`` (Mermaid's message when it couldn't be rendered)."""


@dataclass
class Settings:
    """How diagrams are rendered; Sphinx fills it from conf.py, docutils from register()."""

    config: dict[str, Any] = field(default_factory=dict)
    dark: bool = True
    theme_attribute: str = "data-theme"
    engine: str | None = None
    timeout: float | None = None
    cache_dir: str | None = None
    css_url: str | None = None      # plain docutils: link this stylesheet instead of embedding one
    fonts: bool = True              # plain docutils: include the @font-face rules


_settings = Settings()


def align(argument: str) -> str:
    return directives.choice(argument, ("left", "center", "right"))


def _json(argument: str) -> dict:
    try:
        value = json.loads(argument)
    except ValueError as e:
        raise ValueError(f"not JSON: {e}") from None
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


class MermaidDirective(Directive):
    has_content = True
    optional_arguments = 1
    final_argument_whitespace = True
    option_spec = {
        "caption": directives.unchanged,
        "name": directives.unchanged,
        "alt": directives.unchanged,
        "align": align,
        "width": directives.length_or_percentage_or_unitless,
        "scroll": directives.flag,
        "layout": directives.unchanged,
        "config": _json,
        "class": directives.class_option,
    }

    def settings(self) -> Settings:
        return _settings

    def report(self, message: str) -> None:
        """A diagram Mermaid couldn't render: a warning at the directive's line (the page shows an error box)."""
        self.state.document.reporter.warning(f"the mermaid diagram couldn't be rendered: {message}", line=self.lineno)

    def source_path(self, argument: str) -> tuple[Path, str]:
        """The file an argument names, and the name to record as a dependency."""
        base = Path(self.state.document.current_source or ".").parent
        path = (base / argument).resolve()
        return path, str(path)

    def note_dependency(self, path: str) -> None:
        self.state.document.settings.record_dependencies.add(path)

    def run(self) -> list[nodes.Node]:
        if self.arguments and self.content:
            raise self.error("give the diagram as the directive's content or as a file name, not both")
        if self.arguments:
            path, dep = self.source_path(self.arguments[0])
            try:
                source = path.read_text(encoding="utf-8")
            except OSError as e:
                raise self.error(f"can't read the diagram {self.arguments[0]}: {e.strerror or e}") from None
            self.note_dependency(dep)
        else:
            source = "\n".join(self.content)
        if not source.strip():
            raise self.error("a mermaid diagram needs its source as the directive's content or a file name")

        s = self.settings()
        overrides = dict(s.config)
        if "layout" in self.options:
            overrides["layout"] = self.options["layout"]
        if "config" in self.options:
            from .theme import merge
            overrides = merge(overrides, self.options["config"])

        caption = self.options.get("caption", "")
        node = mermaid_diagram(source=source, alt=self.options.get("alt", caption), width=self.options.get("width"))
        try:
            d = render(source, config=overrides, dark=s.dark, theme_attribute=s.theme_attribute, engine=s.engine,
                       timeout=s.timeout, cache_dir=s.cache_dir, svg_id=diagram_id(source.strip("\n"), overrides))
            node["svg"], node["light"], node["svg_id"] = d.svg, d.light, d.svg_id
            node["config"] = overrides
        except RenderError as e:
            node["error"] = str(e)
            node["svg_id"] = diagram_id(source, overrides)
            self.report(str(e))
        node.source, node.line = self.state_machine.get_source_and_line(self.lineno)

        figure = nodes.figure("", node)
        figure["classes"].append("mermaid-diag")
        if "scroll" in self.options:
            figure["classes"].append("mermaid-diag--scroll")
        if "error" in node:
            figure["classes"].append("mermaid-diag--error")
        figure["classes"] += self.options.get("class", [])
        figure["align"] = self.options.get("align", "center")
        if caption:
            parsed, _messages = self.state.inline_text(caption, self.lineno)
            cap = nodes.caption(caption, "", *parsed)
            cap.source, cap.line = node.source, node.line
            figure += cap
        self.add_name(figure)
        return [figure]


# ---- HTML -----------------------------------------------------------------------------------------------------

_ID = re.compile(r"\bmd-[0-9a-f]{10}\b")


def unique_svg(node: mermaid_diagram, used: set[str]) -> str:
    """The node's SVG, with its id changed if another diagram on the page already has it."""
    svg, svg_id = node["svg"], node["svg_id"]
    if svg_id not in used:
        used.add(svg_id)
        return svg
    n = 2
    while f"{svg_id}-{n}" in used:
        n += 1
    new = f"{svg_id}-{n}"
    used.add(new)
    return svg.replace(svg_id, new)


def html_markup(node: mermaid_diagram, used: set[str]) -> str:
    if "error" in node:
        return (f'<p class="mermaid-diag__message">This diagram couldn\'t be drawn: {html.escape(node["error"])}</p>'
                f'<pre class="mermaid-diag__source">{html.escape(node["source"])}</pre>')
    svg = unique_svg(node, used)
    attrs = ' role="img"'
    if node.get("alt"):
        attrs += f' aria-label="{html.escape(node["alt"], quote=True)}"'
    style = ""
    if node.get("width"):
        width = node["width"]
        if re.fullmatch(r"[\d.]+", str(width)):
            width = f"{width}px"
        style = f' style="max-width:{width}"'
        svg = re.sub(r'(<svg\b[^>]*?)\sstyle="max-width:[^"]*"', r"\1", svg, count=1)
    # Mermaid's own role is "graphics-document document"; the figure's img role with the caption names it.
    return f"<div class=\"mermaid-diag__canvas\"{attrs}{style}>{svg}</div>"


def _docutils_visit_html(self, node: mermaid_diagram) -> None:
    if not getattr(self, "_mermaid_diag_css", False):
        self._mermaid_diag_css = True
        if _settings.css_url:
            self.head.append(f'<link rel="stylesheet" href="{html.escape(_settings.css_url, quote=True)}" />\n')
        else:
            from .assets import figure_css, font_face_css
            css = (font_face_css(None) + "\n" if _settings.fonts else "") + figure_css()
            self.head.append(f"<style>\n{css}\n</style>\n")
    used = self.__dict__.setdefault("_mermaid_diag_ids", set())
    self.body.append(html_markup(node, used))
    raise nodes.SkipNode


def _visit_latex_source(self, node: mermaid_diagram) -> None:
    """docutils' LaTeX writer: the diagram's source, verbatim."""
    self.out.append("\n\\begin{verbatim}\n" + node["source"] + "\n\\end{verbatim}\n")
    raise nodes.SkipNode


def _visit_man_source(self, node: mermaid_diagram) -> None:
    """docutils' man page writer: the diagram's source, unfilled."""
    text = node["source"].replace("\\", "\\e").replace("\n.", "\n\\&.")
    self.body.append("\n.nf\n" + text + "\n.fi\n")
    raise nodes.SkipNode


def register(*, config: dict | None = None, dark: bool = True, theme_attribute: str = "data-theme",
             engine: str | None = None, timeout: float | None = None, cache_dir: str | os.PathLike | None = None,
             css_url: str | None = None, fonts: bool = True) -> None:
    """Make ``.. mermaid::`` available to docutils (rst2html, docutils.core.publish_*)."""
    global _settings
    _settings = Settings(config=dict(config or {}), dark=dark, theme_attribute=theme_attribute, engine=engine,
                         timeout=timeout, cache_dir=str(cache_dir) if cache_dir else None, css_url=css_url,
                         fonts=fonts)
    directives.register_directive("mermaid", MermaidDirective)
    from docutils.writers import _html_base
    _html_base.HTMLTranslator.visit_mermaid_diagram = _docutils_visit_html
    _html_base.HTMLTranslator.depart_mermaid_diagram = lambda self, node: None
    for module, cls, visit in (("docutils.writers.latex2e", "LaTeXTranslator", _visit_latex_source),
                               ("docutils.writers.manpage", "Translator", _visit_man_source)):
        try:
            mod = __import__(module, fromlist=[cls])
            translator: Callable = getattr(mod, cls)
        except Exception:  # noqa: BLE001 -- a writer that isn't available
            continue
        translator.visit_mermaid_diagram = visit
        translator.depart_mermaid_diagram = lambda self, node: None
