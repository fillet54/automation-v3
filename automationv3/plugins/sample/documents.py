"""What the sample plugin adds to documents: a directive listing the files
the report's runs attached, with how it looks live, in the site and in the
PDF. An example of a plugin's rendering (see framework/plugins.py)::

    .. attached-files::
       :script: BRA/*
"""

import fnmatch
from pathlib import Path

from docutils.parsers.rst import directives


def attached_files(context, options):
    """Every file the runs attached, by run"""
    data = context.data
    if data is None:
        return ""
    runs = [(run, data.files(run)) for run in data.runs
            if fnmatch.fnmatch(run["script"], options.get("script") or "*")]
    return context.render("sample/attached-files.rst",
                          runs=[(run, files) for run, files in runs if files])


CSS = ".ui-document .attached-files li { font-family: var(--ui-font-mono); font-size: 12px; }"
LATEX = r"\newenvironment{sphinxclassattached-files}{\small}{}"


def register(registry):
    registry.directive("attached-files", attached_files, {"script": directives.unchanged})
    registry.snippets(Path(__file__).parent / "snippets")
    registry.css(CSS)
    registry.latex(LATEX)
