"""A report as a formal document: a PDF and the bundle it describes

Exporting a report freezes it (no more runs go into it until it is
reopened) and writes report-<id>.zip::

    report-<id>/
      report-<id>/      the report folder, as the store keeps it
      template/         the document template it was rendered with
      MANIFEST.sha256   a SHA-256 for every file in the two folders above
      report.rst        the document's body, generated from the report
      report.tex        the whole document, for LaTeX
      report.pdf

The PDF prints the manifest's own SHA-256, so the bundle can be checked
against the document. The manifest leaves out the files generated from
it (report.rst, report.tex and the PDF).

The document is the template's front matter (title page, contents,
signatures, applicable and reference documents) and then the report:
its identification, summary, open issues, requirements and results.
Only failures are spelled out; everything else about a run is in the
bundle.

Everything comes from the report folder, so a report can be exported
without a server or database. The document's title is the report's
name; its other fields live in report.json under "document"::

    {"number", "revision", "author",
     "signatures": {role: name},
     "documents": [{"kind": "applicable" | "reference",
                    "number", "revision", "title"}]}

A template is a folder holding template.json (company, marking,
document_type and the signature roles), document.tex (a Jinja template,
see the built-in one), optionally body.rst (the body; see rst_template.py)
and the files they include, such as logo.pdf. A
workspace keeps its own in a report/ folder beside its rvts/ folder;
without one, the built-in template is used.
"""

import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import zipfile
from types import SimpleNamespace
from pathlib import Path

import jinja2
from docutils import nodes
from docutils.core import publish_doctree, publish_parts
from docutils.utils import SystemMessage

from . import rollup, rst_template, store
from .data import KINDS, ReportData, duration  # noqa: F401
from .rst_template import Rst, indent, literal, text  # noqa: F401

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


# The model: everything the document says, from the report folder

def model(root, report_id):
    try:
        data = ReportData(root, report_id)
    except LookupError as e:
        raise ExportError(str(e)) from e
    return {
        "report": data.report,
        "document": data.document,
        "rows": data.combinations,
        "requirements": data.requirements,
        "runs": data.runs,
        "first_run": data.first_run,
        "last_run": data.last_run,
        "environments": data.environments(),
    }


# The body, as reStructuredText, from the template's body.rst

BODY = "body.rst"
# A verdict is written with a role of its own name (see body.rst)
VERDICTS = ("pass", "fail", "error", "incomplete", "outdated", "unfinished",
            "green", "red", "partial", "untested")


def combination(row):
    parts = [row["script"]]
    if row["environment"]:
        parts.append(row["environment"])
    if row["variation"]:
        parts.append(row["variation"])
    return " / ".join(parts)


def seconds(value):
    if value is None:
        return ""
    return f"{value:.1f} s" if value < 600 else f"{value / 60:.1f} min"


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def stamp(iso):
    return iso.replace("T", " ").replace("+00:00", " UTC") if iso else ""


def verdict(state):
    if state in VERDICTS:
        return Rst(f":{state}:`{state}`")
    return Rst(f"**{text(state)}**")


def why(row):
    """What went wrong with a combination, after its verdict"""
    failure = row["failure"]
    if failure:
        return Rst((f" at {text(failure['step'])}" if failure["step"] else "")
                   + (f": {text(failure['message'])}" if failure["message"] else ""))
    if row["state"] == "incomplete":
        return Rst(": steps are still to be written (TBD)")
    if row["state"] == "outdated":
        ran = ", ".join(f"{n} {v}" for n, v in sorted(row["outdated"].items()))
        return Rst(f": {text(row['latest'].get('outcome'))} on {text(ran)}, "
                   "not the report's versions")
    return Rst("")


def requirement(value):
    """A requirement's text: as the rst it is, in a requirement container,
    when it stands on its own as body text; else as plain text"""
    if not value:
        return Rst("*text not recorded*")
    if not body_only(value):
        return text(value)
    return Rst(".. container:: requirement\n\n" + indent(Rst(value.strip()), 3, first=True))


def body_only(value):
    """Whether rst `value` parses cleanly with plain docutils, to nothing
    but body elements (no sections, which a table cell can't hold)"""
    problems = io.StringIO()
    try:
        tree = publish_doctree(value, settings_overrides={
            "warning_stream": problems, "report_level": 2, "halt_level": 2,
            "doctitle_xform": False, "file_insertion_enabled": False,
            "raw_enabled": False})
    except SystemMessage:
        return False
    return not problems.getvalue() and not any(
        tree.findall(lambda n: isinstance(n, (nodes.section, nodes.transition,
                                              nodes.title, nodes.target))))


def body_template(template=None):
    """The body template: the document template's own body.rst, else the
    built-in one"""
    folders = [str(template)] if template and Path(template) != BUILTIN_TEMPLATE else []
    env = rst_template.environment(jinja2.FileSystemLoader([*folders, str(BUILTIN_TEMPLATE)]))
    env.filters.update(combination=combination, seconds=seconds, plural=plural,
                       stamp=stamp, verdict=verdict, why=why, requirement=requirement)
    return env.get_template(BODY)


def render_rst(m, manifest_hash, exported, template=None):
    report, rows = m["report"], m["rows"]
    used = rollup.used_uuts(m["runs"])
    colors = [r["color"] for r in m["requirements"]]
    states = [r["state"] for r in rows]
    summary = [(f"Requirements {c}", colors.count(c))
               for c in ("green", "red", "partial", "untested") if m["requirements"]]
    summary += [(f"Combinations {s}", states.count(s))
                for s in dict.fromkeys(["pass", "fail", "error", "incomplete", *states])]
    return body_template(template).render(
        report={"name": "", "workspace": "", "created": "", **report},
        rows=rows,
        requirements=m["requirements"],
        runs=m["runs"],
        first_run=m["first_run"],
        last_run=m["last_run"],
        issues=[r for r in rows if r["state"] != "pass"],
        untested=[r for r in m["requirements"] if r["color"] == "untested"],
        earlier=[r for r in rows if r["earlier"]],
        failures=[r for r in rows if r["failure"]],
        summary=summary,
        versions=[f"{name} {v['id']} ({v.get('digest', '')[:12]})"
                  for name, v in (report.get("uut_versions") or {}).items() if name in used],
        environments=[f"{env or 'none'}: {', '.join(p) or 'platform not recorded'}"
                      for env, p in m["environments"].items()],
        exported=exported,
        manifest_hash=manifest_hash,
        verdicts=VERDICTS,
    )


def rst_to_latex(rst):
    problems = io.StringIO()
    try:
        parts = publish_parts(rst, writer_name="latex", settings_overrides={
            "table_style": ["booktabs"],
            "use_latex_toc": True,
            "doctitle_xform": False,
            "legacy_column_widths": False,
            "use_latex_citations": True,
            "report_level": 2,
            "halt_level": 2,  # the body is generated: any problem in it is a bug
            "warning_stream": problems,
        })
    except SystemMessage as e:
        raise ExportError(f"The document's body is malformed: {e}") from e
    if problems.getvalue():
        raise ExportError(f"The document's body is malformed: {problems.getvalue()}")
    return parts


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


def render_tex(m, template, body, manifest_hash, exported):
    settings = template_settings(template)
    document = m["document"]
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
        report_id=latex(m["report"]["id"]),
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


def bundle(root, report_id, template, out_dir):
    """Write report-<id>.zip into `out_dir`; returns its path"""
    m = model(root, report_id)
    exported = store.now_iso()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        report_name = f"report-{report_id}"
        copy_report(root, report_id, work / report_name)
        shutil.copytree(template, work / "template")
        if not (work / "template" / BODY).exists():  # it used the built-in body
            shutil.copy(BUILTIN_TEMPLATE / BODY, work / "template" / BODY)
        manifest_text = manifest(work, [report_name, "template"])
        (work / "MANIFEST.sha256").write_text(manifest_text)
        manifest_hash = hashlib.sha256(manifest_text.encode()).hexdigest()

        rst = render_rst(m, manifest_hash, exported, template)
        (work / "report.rst").write_text(rst)
        tex = render_tex(m, template, rst_to_latex(rst), manifest_hash, exported)
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
            for name in ["report.pdf", "MANIFEST.sha256", "report.rst", "report.tex"]:
                zf.write(work / name, f"{report_name}/{name}")
            for folder in [report_name, "template"]:
                for path in sorted((work / folder).rglob("*")):
                    if path.is_file():
                        zf.write(path, f"{report_name}/{path.relative_to(work).as_posix()}")
        partial.replace(target)
    return target


def unfinished(root, report_id):
    return [r for r in store.list_runs(root, report_id) if r.get("outcome") is None]


def export(root, report_id, out_dir=None, template=None, snapshots=None):
    """Freeze the report and write its bundle; returns the zip's path.
    `out_dir` defaults to the report's exports/ folder. `snapshots` (see
    jobs.requirement_snapshots) fill in requirements the report tracked
    before the database knew them.

    Raises ExportError, leaving the report as it was, if a run hasn't
    finished or the PDF can't be made."""
    report = store.load_report(root, report_id)
    if report is None:
        raise ExportError(f"No report {report_id} in {root}")
    waiting = unfinished(root, report_id)
    if waiting:
        raise ExportError(f"{len(waiting)} runs haven't finished: wait for them, "
                          "or remove them, before exporting")
    template = Path(template or BUILTIN_TEMPLATE)
    if not (template / "template.json").is_file():
        raise ExportError(f"{template} isn't a report template: it has no template.json")
    was_frozen, kept = store.is_frozen(report), report.get("requirement_snapshots") or {}
    added = {k: v for k, v in (snapshots or {}).items()
             if k in report.get("requirements", {}) and k not in kept}
    store.update_report(root, report_id, frozen=True,
                        requirement_snapshots={**kept, **added})
    try:
        return bundle(root, report_id, template,
                      out_dir or store.report_dir(root, report_id) / EXPORTS)
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
