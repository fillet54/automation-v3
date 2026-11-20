"""mermaid-diag: Mermaid 12 diagrams rendered at build time, for the command line, docutils and Sphinx.

    from mermaid_diag import render
    diagram = render("flowchart LR\n  A --> B")
    diagram.svg     # inline SVG that follows light and dark mode
    diagram.png()   # needs the [png] extra

Sphinx: add "mermaid_diag.sphinx" to extensions. docutils: call mermaid_diag.docutils.register().
"""

__version__ = "0.1.0"

from .api import MERMAID_VERSION, Diagram, RenderError, diagram_id, picture_svg, render, render_mode  # noqa: E402

__all__ = ["__version__", "MERMAID_VERSION", "Diagram", "RenderError", "diagram_id", "picture_svg", "render", "render_mode"]
