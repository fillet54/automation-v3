"""A report as a formal document: a static site, a PDF, and the bundle

Freezing a report makes its data read-only and builds its site and PDF
with Sphinx (see build.py and sphinx_ext.py); a frozen report serves
its site. Exporting writes report-<id>.zip (see `bundle`)::

    report-<id>/
      report-<id>/      the report folder, as the store keeps it, holding
                        the document's source (report.rst) and its
                        template (template/)
      MANIFEST.sha256   a SHA-256 for every file in the report folder
      report.pdf, report.tex
      site/             the static site

The PDF prints the manifest's own SHA-256, so the bundle can be checked
against the document. The manifest leaves out what is built from it.

The document is the template's front matter (title page, contents,
signatures, applicable and reference documents) and then report.rst: its
prose, and the report directives (see documents/report.py) resolved
against the report's data. The directives stay in report.rst, and the
data they read is in the bundle, so the document can be built again from
the bundle alone.

The document's title is the report's name; its other fields live in
report.json under "document"::

    {"number", "revision", "author",
     "signatures": {role: name},
     "documents": [{"kind": "applicable" | "reference",
                    "number", "revision", "title"}]}

A template is a folder holding template.json (company, marking,
document_type and the signature roles), latex.tex_t (Sphinx's LaTeX
template, with the title page; see the built-in one), report.rst (the
document a new report starts from), optionally snippets/ (overriding the built-in ones, see
documents/template.py) and the files they include, such as logo.pdf. A
workspace keeps its own in a report/ folder beside its scripts folder;
without one, the built-in template is used. A report copies its
workspace's template when it is created, so its look can't drift.
"""

import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote

from docutils import nodes

from ...documents import core
from ...documents.template import Snippets
from . import build, store
from ..util import replace
from .build import (  # noqa: F401
    BUILTIN_TEMPLATE,
    EXPORTS,
    LATEX_SPECIAL,
    SOURCE,
    TEMPLATE,
    ExportError,
    build_pdf,
    latex,
    numbered,
    report_template,
    sha256,
    source,
    template_settings,
)
from .data import KINDS, Links, ReportData, document_fields  # noqa: F401


# The report's document fields

def missing_fields(report):
    """Names of the document fields a formal document needs and the
    report hasn't set"""
    fields = {**(report.get("document") or {}), "title": report.get("name")}
    return [name for name in ("title", "number", "revision", "author")
            if not fields.get(name)]


def set_document(root, report_id, **fields):
    """Set some of the report's document fields; a title renames the
    report. A frozen report can't change."""
    report = store.load_report(root, report_id)
    if store.is_frozen(report):
        raise ExportError("The report is frozen: reopen it to change it")
    if "title" in fields:
        rename(root, report_id, fields.pop("title"))
    document = {**(report.get("document") or {}), **fields}
    document.pop("title", None)  # older reports kept a title of their own
    return store.update_report(root, report_id, document=document)


def rename(root, report_id, name):
    """Change the report's name, which is its document's title too"""
    name = " ".join((name or "").split())
    if not name:
        raise ExportError("A report needs a name")
    if store.is_frozen(store.load_report(root, report_id)):
        raise ExportError("The report is frozen: reopen it to rename it")
    return store.update_report(root, report_id, name=name)


def parse_documents(text, kind):
    """Documents from lines of NUMBER | REVISION | TITLE"""
    documents = []
    for line in text.splitlines():
        if not line.strip():
            continue
        number, revision, title = ([*(p.strip() for p in line.split("|", 2)), "", ""])[:3]
        documents.append({"kind": kind, "number": number, "revision": revision,
                          "title": title})
    return documents


def format_documents(documents, kind):
    return "\n".join(f"{d['number']} | {d['revision']} | {d['title']}"
                     for d in documents if d.get("kind") == kind)


# Templates

def find_template(workspace_root=None):
    """The template folder of a workspace (its scripts folder's sibling
    report/), else the built-in one"""
    if workspace_root:
        candidate = Path(workspace_root).parent / "report"
        if (candidate / "template.json").is_file():
            return candidate
    return BUILTIN_TEMPLATE


# A report's own template, and its document's source

def install_template(root, report_id, template=None, with_source=True):
    """Copy `template` (default: the built-in one) into the report, and,
    with `with_source`, its report.rst as the report's document"""
    template = Path(template or report_template(root, report_id))
    folder = store.report_dir(root, report_id)
    target = folder / TEMPLATE
    if target.resolve() == template.resolve():
        return target
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(template, target)
    if with_source:
        found = template / SOURCE
        shutil.copy(found if found.is_file() else BUILTIN_TEMPLATE / SOURCE, folder / SOURCE)
    return target


def set_source(root, report_id, text):
    """Change the report's document source; a frozen report can't"""
    if store.is_frozen(store.load_report(root, report_id)):
        raise ExportError("The report is frozen: reopen it to change its document")
    (store.report_dir(root, report_id) / SOURCE).write_text(text, encoding="utf-8")


def context(root, report_id, host=core.EXPORT, links=None, status=None, data=None, **extra):
    """The Context a report's document is resolved with"""
    from ...framework.plugins import load_plugins
    load_plugins()  # their directives, roles, filters and snippets
    if data is None:
        data = ReportData(root, report_id, **({"status": status} if status else {}),
                          links=links)
    return core.Context(data=data, host=host,
                        snippets=Snippets([report_template(root, report_id) / "snippets"]),
                        **extra)


class ServerLinks(Links):
    """Links from an exported document to the server's pages: absolute,
    from the server's base URL, so they work wherever the document is
    read. Requirements open in the context the report tested them in."""

    def __init__(self, base_url):
        self.base = (base_url or "").rstrip("/")

    def requirement(self, id, snapshot):
        if not self.base or not snapshot or not snapshot.get("spec"):
            return None
        return (f"{self.base}/requirements/spec/{quote(snapshot['context'], safe='@')}/"
                f"{quote(snapshot['spec'])}/?req={quote(id)}")


# The document

def problems(document):
    """The parse and resolve problems in a resolved document"""
    return [m.astext() for m in document.findall(nodes.system_message) if m["level"] >= 2]


def render_document(context, text):
    """The resolved doctree of a report document's source `text`"""
    return core.resolved(core.parse(text, source_path=SOURCE), context)


# Freezing, and the bundle

def exports_dir(root, report_id):
    return store.report_dir(root, report_id) / EXPORTS


def unfinished(root, report_id):
    return [r for r in store.list_runs(root, report_id) if r.get("outcome") is None]


def freeze(root, report_id, snapshots=None, base_url="", template=None, wait=False):
    """Freeze the report and build its site and PDF (see build.py): in the
    background, or with `wait`, before returning its status. `snapshots`
    (see runs.requirement_snapshots) fill in requirements the report
    tracked before the database knew them; `template` replaces the
    report's own; `base_url` is the server's, for links to its
    requirement pages.

    Raises ExportError, leaving the report as it was, if it can't be
    frozen. A build that fails leaves it frozen, with the error in its
    status, to rebuild once fixed."""
    report = store.load_report(root, report_id)
    if report is None:
        raise ExportError(f"No report {report_id} in {root}")
    waiting = unfinished(root, report_id)
    if waiting:
        raise ExportError(f"{len(waiting)} runs haven't finished: wait for them, "
                          "or remove them, before freezing")
    if template is not None:
        if not (Path(template) / "template.json").is_file():
            raise ExportError(f"{template} isn't a report template: it has no template.json")
        install_template(root, report_id, template, with_source=False)
    kept = report.get("requirement_snapshots") or {}
    added = {k: v for k, v in (snapshots or {}).items()
             if k in report.get("requirements", {}) and k not in kept}
    store.update_report(root, report_id, frozen=True, requirement_snapshots={**kept, **added})
    build.clear(root, report_id)
    if wait:
        return build.build(root, report_id, base_url)
    build.start(root, report_id, base_url)
    return build.status(root, report_id)


def bundle(root, report_id, out_dir=None):
    """report-<id>.zip of a built report in `out_dir` (default: the
    report's exports/ folder); returns its path::

        report-<id>/
          report-<id>/      the report folder: data, document and template
          MANIFEST.sha256   a SHA-256 for every file of the report folder
          report.pdf, report.tex
          site/             the static site
    """
    found = build.status(root, report_id) or {}
    if found.get("state") != "done":
        raise ExportError("The report hasn't been built: freeze it, and wait for its build"
                          + (f" (it failed: {found['error']})" if found.get("error") else ""))
    folder, built = store.report_dir(root, report_id), build.build_dir(root, report_id)
    name = f"report-{report_id}"
    out_dir = Path(out_dir) if out_dir is not None else exports_dir(root, report_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{name}.zip"
    # a temporary name of its own, so two exports at once can't mix
    fd, partial = tempfile.mkstemp(dir=out_dir, prefix=f".{name}.", suffix=".zip.tmp")
    os.close(fd)
    try:
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in ("MANIFEST.sha256", "report.pdf", "report.tex"):
                zf.write(built / item, f"{name}/{item}")
            for path in build.files(root, report_id):
                zf.write(path, f"{name}/{name}/{path.relative_to(folder).as_posix()}")
            for path in sorted((built / "site").rglob("*")):
                if path.is_file():
                    zf.write(path,
                             f"{name}/site/{path.relative_to(built / 'site').as_posix()}")
        os.chmod(partial, 0o644)
        replace(partial, target)
    except BaseException:
        Path(partial).unlink(missing_ok=True)
        raise
    return target


def export(root, report_id, out_dir=None, template=None, snapshots=None, base_url=""):
    """Freeze the report, build it (waiting) and write its bundle; returns
    the zip's path. `out_dir` defaults to the report's exports/ folder.
    Raises ExportError if it can't be frozen (leaving it as it was) or
    the build fails (leaving it frozen)."""
    found = freeze(root, report_id, snapshots, base_url, template, wait=True)
    if found["state"] != "done":
        raise ExportError(found.get("error") or "The build failed")
    return bundle(root, report_id, out_dir)


def reopen(root, report_id):
    if store.load_report(root, report_id) is None:
        raise ExportError(f"No report {report_id} in {root}")
    store.set_frozen(root, report_id, False)
    build.clear(root, report_id)


def exports(root, report_id):
    """The report's exported bundles, newest first"""
    folder = exports_dir(root, report_id)
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
