"""Sphinx configuration for the Automation v3 documentation

Build with `make html` in this folder (or `sphinx-build -b html . _build/html`).
The Read the Docs theme is restyled by _static/css/notebook.css to the
"research notebook" look of the web UI.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE / "_ext"))

from automationv3 import __version__  # noqa: E402

# -- Project ---------------------------------------------------------------

project = "Automation v3"
author = "Phillip Gomez"
copyright = "2023–2026, Phillip Gomez"
version = release = __version__

# -- General ---------------------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.todo",
    "sphinx_rtd_theme",
    "notebook",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "requirements", "Thumbs.db", ".DS_Store"]

# Script code is edn/Lisp: highlight it as Clojure
highlight_language = "clojure"
pygments_style = "default"  # colours come from notebook.css

autodoc_member_order = "bysource"
autodoc_default_options = {"members": True}
autodoc_typehints = "none"

todo_include_todos = True

rst_prolog = """
.. role:: edn(code)
   :language: clojure
"""

# -- HTML ------------------------------------------------------------------

html_theme = "sphinx_rtd_theme"
html_title = "Automation v3"
html_short_title = "Automation v3"
html_static_path = ["_static"]
html_css_files = [
    "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600"
    "&family=Inter:wght@400;500;600;700"
    "&family=Source+Serif+4:opsz,wght@8..60,400;8..60,500&display=swap",
    "css/notebook.css",
]
html_theme_options = {
    "collapse_navigation": False,
    "navigation_depth": 3,
    "titles_only": False,
    "style_external_links": False,
    "prev_next_buttons_location": "bottom",
}
html_show_sourcelink = False
html_show_sphinx = False
