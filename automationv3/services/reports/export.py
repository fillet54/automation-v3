"""A report as a formal document: a PDF and the bundle it describes

Exporting a report freezes it (no more runs go into it until it is
reopened) and writes report-<id>.zip::

    report-<id>/
      report-<id>/      the report folder, as the store keeps it, holding
                        the document's source (report.rst) and its
                        template (template/)
      MANIFEST.sha256   a SHA-256 for every file in the report folder
      report.tex        the whole document, for LaTeX
      report.pdf

The PDF prints the manifest's own SHA-256, so the bundle can be checked
against the document. The manifest leaves out the files generated from
it (report.tex and the PDF).

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
document_type and the signature roles), document.tex (a Jinja template,
see the built-in one), report.rst (the document a new report starts
from), optionally snippets/ (overriding the built-in ones, see
documents/template.py) and the files they include, such as logo.pdf. A
workspace keeps its own in a report/ folder beside its rvts/ folder;
without one, the built-in template is used. A report copies its
workspace's template when it is created, so its look can't drift.
"""

import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import jinja2
from docutils import nodes

from ...documents import core
from ...documents.template import Snippets
from . import store
from .data import KINDS, Links, ReportData  # noqa: F401

BUILTIN_TEMPLATE = Path(__file__).parent / "template"
EXPORTS = "exports"  # a report folder's exported bundles; never bundled


class ExportError(Exception):
    pass


# The report's document fields

def document_fields(report):
    """The report's document fields, with defaults for any not set"""
    return ReportData.document.fget(SimpleNamespace(
        report=report, name=report.get("name") or f"Report {report['id'][:8]}"))


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
    """The template folder of a workspace (its rvts/ folder's sibling
    report/), else the built-in one"""
    if workspace_root:
        candidate = Path(workspace_root).parent / "report"
        if (candidate / "template.json").is_file():
            return candidate
    return BUILTIN_TEMPLATE


def template_settings(template):
    settings = json.loads((Path(template) / "template.json").read_text())
    settings.setdefault("roles", [])
    return settings


# A report's own template, and its document's source

TEMPLATE = "template"   # in a report folder: the template it renders with
SOURCE = "report.rst"   # in a report folder: its document's source


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


def report_template(root, report_id):
    """The template the report renders with: its own copy, else (reports
    made before reports kept one) the built-in one"""
    own = store.report_dir(root, report_id) / TEMPLATE
    return own if (own / "template.json").is_file() else BUILTIN_TEMPLATE


def source(root, report_id):
    """The report's document source"""
    own = store.report_dir(root, report_id) / SOURCE
    if own.is_file():
        return own.read_text()
    found = report_template(root, report_id) / SOURCE
    return (found if found.is_file() else BUILTIN_TEMPLATE / SOURCE).read_text()


def set_source(root, report_id, text):
    """Change the report's document source; a frozen report can't"""
    if store.is_frozen(store.load_report(root, report_id)):
        raise ExportError("The report is frozen: reopen it to change its document")
    (store.report_dir(root, report_id) / SOURCE).write_text(text)


def context(root, report_id, host=core.EXPORT, links=None, status=None, **extra):
    """The Context a report's document is resolved with"""
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

LATEX = {
    "table_style": ["booktabs"],
    "use_latex_toc": True,
    "legacy_column_widths": False,
    "use_latex_citations": True,
}


def problems(document):
    """The parse and resolve problems in a resolved document"""
    return [m.astext() for m in document.findall(nodes.system_message) if m["level"] >= 2]


def render_document(context, text):
    """The resolved doctree of a report document's source `text`"""
    return core.resolved(core.parse(text, source_path=SOURCE), context)


def document_latex(context, text):
    """docutils' LaTeX parts for a report document; ExportError if its
    source has problems"""
    document = render_document(context, text)
    found = problems(document)
    if found:
        raise ExportError("The document has problems: " + "; ".join(found))
    return core.write(document, "latex", LATEX)


# The whole document, as LaTeX

LATEX_SPECIAL = {
    "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$", "&": r"\&",
    "#": r"\#", "^": r"\textasciicircum{}", "_": r"\_", "~": r"\textasciitilde{}",
    "%": r"\%",
}


def latex(value):
    return "".join(LATEX_SPECIAL.get(c, c) for c in str(value if value is not None else ""))


def numbered(documents, kind, prefix):
    of_kind = [d for d in documents if d["kind"] == kind]
    return [{"id": f"{prefix}{n}",
             **{k: latex(d.get(k, "")) for k in ("number", "revision", "title")}}
            for n, d in enumerate(of_kind, 1)]


def render_tex(data, template, body, manifest_hash, exported):
    settings = template_settings(template)
    document = data.document
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template)),
        block_start_string="((*", block_end_string="*))",
        variable_start_string="(((", variable_end_string=")))",
        comment_start_string="((#", comment_end_string="#))",
        trim_blocks=True, lstrip_blocks=True, autoescape=False,
        undefined=jinja2.StrictUndefined, keep_trailing_newline=True,
    )
    names = document["signatures"]
    roles = list(settings["roles"]) + [r for r in names if r not in settings["roles"]]
    return env.get_template("document.tex").render(
        company=latex(settings.get("company", "")),
        marking=latex(settings.get("marking", "")),
        document_type=latex(settings.get("document_type", "Test Report")),
        title=latex(document["title"]),
        number=latex(document["number"] or "-"),
        revision=latex(document["revision"] or "-"),
        author=latex(document["author"]),
        date=latex(exported[:10]),
        report_id=latex(data.id),
        manifest_hash=latex(manifest_hash),
        signatures=[(latex(role), latex(names.get(role, ""))) for role in roles],
        applicable=numbered(document["documents"], "applicable", "AD"),
        reference=numbered(document["documents"], "reference", "RD"),
        body=body["body"],
        requirements=body["requirements"],
        fallbacks=body["fallbacks"],
        pdfsetup=body["pdfsetup"],
    )


# The bundle

def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest(folder, names):
    """MANIFEST.sha256 text for every file under `folder`/name, by
    relative path"""
    lines = []
    for name in names:
        for path in sorted((folder / name).rglob("*")):
            if path.is_file():
                lines.append(f"{sha256(path)}  {path.relative_to(folder).as_posix()}")
    return "\n".join(lines) + "\n"


def copy_report(root, report_id, dest):
    shutil.copytree(store.report_dir(root, report_id), dest,
                    ignore=lambda folder, names: [EXPORTS] if Path(folder) ==
                    store.report_dir(root, report_id) else [])


def build_pdf(folder):
    """report.pdf from report.tex in `folder`, with latexmk"""
    if shutil.which("latexmk") is None:
        raise ExportError("latexmk is needed to make the PDF: install a TeX "
                          "distribution (e.g. TeX Live)")
    result = subprocess.run(
        ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error",
         "-file-line-error", "report.tex"],
        cwd=folder, capture_output=True, text=True)
    if result.returncode != 0 or not (folder / "report.pdf").exists():
        log = (folder / "report.log")
        lines = log.read_text(errors="replace").splitlines() if log.exists() else []
        errors = [line for line in lines if line.startswith("!") or ".tex:" in line]
        raise ExportError("LaTeX couldn't make the PDF: "
                          + ("; ".join(errors[:5]) or result.stdout[-500:]))


def bundle(root, report_id, template, out_dir, base_url=""):
    """Write report-<id>.zip into `out_dir`; returns its path"""
    exported = store.now_iso()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        report_name = f"report-{report_id}"
        folder = work / report_name
        copy_report(root, report_id, folder)
        text = source(root, report_id)
        (folder / SOURCE).write_text(text)
        if Path(template).resolve() != (folder / TEMPLATE).resolve():
            shutil.rmtree(folder / TEMPLATE, ignore_errors=True)
            shutil.copytree(template, folder / TEMPLATE)  # what it is rendered with
        manifest_text = manifest(work, [report_name])
        (work / "MANIFEST.sha256").write_text(manifest_text)
        manifest_hash = hashlib.sha256(manifest_text.encode()).hexdigest()

        found = context(work, report_name, links=ServerLinks(base_url),
                        exported=exported, manifest_hash=manifest_hash)
        tex = render_tex(found.data, template, document_latex(found, text),
                         manifest_hash, exported)
        build = work / "build"
        shutil.copytree(template, build)
        (build / "report.tex").write_text(tex)
        build_pdf(build)
        (work / "report.tex").write_text(tex)
        shutil.copy(build / "report.pdf", work / "report.pdf")

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{report_name}.zip"
        partial = target.with_suffix(".zip.tmp")
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in ["report.pdf", "MANIFEST.sha256", "report.tex"]:
                zf.write(work / name, f"{report_name}/{name}")
            for path in sorted(folder.rglob("*")):
                if path.is_file():
                    zf.write(path, f"{report_name}/{path.relative_to(work).as_posix()}")
        partial.replace(target)
    return target


def unfinished(root, report_id):
    return [r for r in store.list_runs(root, report_id) if r.get("outcome") is None]


def export(root, report_id, out_dir=None, template=None, snapshots=None, base_url=""):
    """Freeze the report and write its bundle; returns the zip's path.
    `out_dir` defaults to the report's exports/ folder. `snapshots` (see
    jobs.requirement_snapshots) fill in requirements the report tracked
    before the database knew them. `template` overrides the report's own;
    `base_url` is the server's, for links to its requirement pages.

    Raises ExportError, leaving the report as it was, if a run hasn't
    finished or the PDF can't be made."""
    report = store.load_report(root, report_id)
    if report is None:
        raise ExportError(f"No report {report_id} in {root}")
    waiting = unfinished(root, report_id)
    if waiting:
        raise ExportError(f"{len(waiting)} runs haven't finished: wait for them, "
                          "or remove them, before exporting")
    template = Path(template or report_template(root, report_id))
    if not (template / "template.json").is_file():
        raise ExportError(f"{template} isn't a report template: it has no template.json")
    was_frozen, kept = store.is_frozen(report), report.get("requirement_snapshots") or {}
    added = {k: v for k, v in (snapshots or {}).items()
             if k in report.get("requirements", {}) and k not in kept}
    store.update_report(root, report_id, frozen=True,
                        requirement_snapshots={**kept, **added})
    try:
        return bundle(root, report_id, template,
                      out_dir or store.report_dir(root, report_id) / EXPORTS, base_url)
    except Exception:
        store.update_report(root, report_id, frozen=was_frozen, requirement_snapshots=kept)
        raise


def reopen(root, report_id):
    if store.load_report(root, report_id) is None:
        raise ExportError(f"No report {report_id} in {root}")
    store.set_frozen(root, report_id, False)


def exports(root, report_id):
    """The report's exported bundles, newest first"""
    folder = store.report_dir(root, report_id) / EXPORTS
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
