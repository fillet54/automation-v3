"""Sphinx configuration for the automation documentation

Build with `make html` in this folder (or `sphinx-build -b html . _build/html`).
The theme (_themes/automation) makes the docs a page of the web UI: its
header, side column and stylesheet (ui.css, copied from the web app). Served
by the server at /docs, they also get its brand, nav, markings and fonts.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE / "_ext"))

from automationv3 import __version__  # noqa: E402
from automationv3.web.ui import GOOGLE_FONTS  # noqa: E402

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
    "diagrams",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "requirements", "Thumbs.db", ".DS_Store"]

# Script code is edn/Lisp: highlight it as Clojure
highlight_language = "clojure"  # colours come from the theme's docs.css

autodoc_member_order = "bysource"
autodoc_default_options = {"members": True}
autodoc_typehints = "none"

todo_include_todos = True

rst_prolog = """
.. role:: edn(code)
   :language: clojure
"""

# -- HTML ------------------------------------------------------------------

html_theme = "automation"
html_theme_path = ["_themes"]
html_theme_options = {"brand": "automation", "fonts_css": GOOGLE_FONTS}
html_title = html_short_title = "automation"
# The web UI's stylesheet, so the docs share its tokens and shell
html_static_path = [str(HERE.parent / "automationv3" / "web" / "static" / "css" / "ui.css")]
html_show_sourcelink = False
html_show_sphinx = False
