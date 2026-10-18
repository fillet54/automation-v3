"""Sphinx configuration for a report's build (see services/reports/build.py)

The project's own conf.py is two lines: it imports this, then reads the
build's settings (build.json, beside it) with `configure`.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATIC = HERE.parent / "web" / "static" / "css"


def configure(namespace, settings_file):
    """Fill a conf.py's namespace from the build's settings"""
    settings = json.loads(Path(settings_file).read_text())
    namespace.update(
        project=settings["title"],
        author=settings["author"],
        extensions=["automationv3.documents.sphinx"],
        root_doc="index",
        exclude_patterns=settings.get("exclude", []),
        templates_path=[settings["template"]],
        html_theme="report",
        html_theme_path=[str(HERE / "sphinx_theme")],
        html_static_path=[str(STATIC)],
        html_title=settings["title"],
        html_short_title=settings["title"],
        html_copy_source=False,
        html_permalinks=False,
        html_show_sourcelink=False,
        html_show_sphinx=False,
        html_domain_indices=False,
        html_use_index=False,
        latex_engine="pdflatex",
        latex_documents=[("index", "report.tex", settings["title"], settings["author"],
                          "howto", False)],
        latex_additional_files=settings.get("latex_files", []),
        latex_elements={"papersize": "a4paper", "pointsize": "10pt"},
        latex_domain_indices=False,
        latex_use_xindy=False,
        highlight_language="none",
        automation_root=settings["root"],
        automation_folder=settings["folder"],
        automation_server_url=settings.get("server_url", ""),
        automation_exported=settings.get("exported", ""),
        automation_manifest_hash=settings.get("manifest_hash", ""),
        automation_snippets=settings.get("snippets", ""),
        automation_latex=settings.get("latex", {}),
    )
