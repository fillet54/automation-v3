"""Sphinx configuration for building a spec (see render.py). Specs bring
no conf.py of their own: this is every spec's."""

extensions = ["automationv3.services.requirements.sphinx"]
project = "spec"
root_doc = "index"
exclude_patterns = ["_build"]
html_theme = "theme"
html_theme_path = ["."]
html_permalinks = False
html_copy_source = False
smartquotes = False
