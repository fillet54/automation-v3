"""Sphinx configuration for the automation documentation

Build with `make html` in this folder (or `sphinx-build -b html . _build/html`).
The theme is paper-ui's ("paper"), the web UI's own look: its header, side
column, stylesheet and IBM Plex fonts. _static/automation-docs.css adds this
project's pieces. Served by the server at /docs, the pages also get its brand,
nav and markings.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE / "_ext"))

from automationv3 import __version__  # noqa: E402

# -- Project ---------------------------------------------------------------

project = "automation"
author = "Phillip Gomez"
copyright = "2023–2026, Phillip Gomez"
version = release = __version__

# -- General ---------------------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.todo",
    "notebook",
    "mermaid_diag.sphinx",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "requirements", "Thumbs.db", ".DS_Store"]

# Script code is edn/Lisp: highlight it as Clojure
highlight_language = "clojure"  # colours come from the theme (paper-ui's docs.css)

autodoc_member_order = "bysource"
autodoc_default_options = {"members": True}
autodoc_typehints = "none"

todo_include_todos = True

# Diagrams (``.. mermaid::``) are drawn at build time by mermaid-diag (../mermaid-diag), as inline SVG that follows
# the theme switcher's light or dark (paper-ui sets data-ui-theme on <html>). No JavaScript on the pages.
mermaid_diag_theme_attribute = "data-ui-theme"

rst_prolog = """
.. role:: edn(code)
   :language: clojure
"""

# -- HTML ------------------------------------------------------------------

html_theme = "paper"
html_theme_options = {"brand": "automation", "line_breaks": "tex"}  # TeX line breaks: paper-ui[linebreaks]
html_title = html_short_title = "automation"
html_static_path = ["_static"]
html_css_files = ["automation-docs.css"]
html_show_sourcelink = False
html_show_sphinx = False
