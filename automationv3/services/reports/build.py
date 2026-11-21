"""Building a frozen report: its static site and its PDF, with Sphinx

Freezing a report makes its data read-only and builds, into the report
folder's build/:

    build/
      MANIFEST.sha256   a SHA-256 for every file of the report folder
                        (its data, its document and its template)
      site/             the static site: the report's document and a page
                        per run; a frozen report serves it
      report.pdf        the document, with the failing runs as appendices
      report.tex
      status.json       {"state": building|done|failed, "started", "ended",
                         "error", "framework"}
      log.txt           what Sphinx and LaTeX said

The build runs in a process of its own (`start`), so the page that froze
the report doesn't wait; `build` is the same, waited for. The PDF prints
the manifest's SHA-256, so a bundle can be checked against its document.

Run as ``python -m automationv3.services.reports.build ROOT REPORT [URL]``.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import store
from .data import ReportData
from ..util import now_iso, write_json

BUILTIN_TEMPLATE = Path(__file__).parent / "template"
TEMPLATE = "template"   # in a report folder: the template it renders with
SOURCE = "report.rst"   # in a report folder: its document's source
BUILD = "build"         # in a report folder: what freezing built
EXPORTS = "exports"     # a report folder's exported bundles; never bundled
SKIP = {BUILD, EXPORTS}  # never part of the report's own files
LATEX_SKIP = {"latex.tex_t", "template.json", "report.rst", "snippets"}


class ExportError(Exception):
    pass


def report_template(root, report_id):
    """The template the report renders with: its own copy, else (reports
    made before reports kept one) the built-in one"""
    own = store.report_dir(root, report_id) / TEMPLATE
    return own if (own / "template.json").is_file() else BUILTIN_TEMPLATE


def template_settings(template):
    settings = json.loads((Path(template) / "template.json").read_text())
    settings.setdefault("roles", [])
    return settings


def source(root, report_id):
    """The report's document source"""
    own = store.report_dir(root, report_id) / SOURCE
    if own.is_file():
        return own.read_text()
    found = report_template(root, report_id) / SOURCE
    return (found if found.is_file() else BUILTIN_TEMPLATE / SOURCE).read_text()


# Values for the PDF's template (latex.tex_t), escaped for LaTeX

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


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def build_dir(root, report_id):
    return store.report_dir(root, report_id) / BUILD


def pdf_path(root, report_id):
    return build_dir(root, report_id) / "report.pdf"


def log_path(root, report_id):
    return build_dir(root, report_id) / "log.txt"


def status(root, report_id):
    """The build's status, or None if the report hasn't been built"""
    path = build_dir(root, report_id) / "status.json"
    return json.loads(path.read_text()) if path.is_file() else None


def set_status(root, report_id, **fields):
    folder = build_dir(root, report_id)
    found = {**(status(root, report_id) or {}), **fields}
    write_json(folder / "status.json", found)
    return found


def clear(root, report_id):
    shutil.rmtree(build_dir(root, report_id), ignore_errors=True)


def site(root, report_id):
    """The built site's folder, or None"""
    found = build_dir(root, report_id) / "site"
    return found if (found / "index.html").is_file() else None


# The manifest: every file of the report folder, but what is built from it

def files(root, report_id):
    folder = store.report_dir(root, report_id)
    return [p for p in sorted(folder.rglob("*"))
            if p.is_file() and p.relative_to(folder).parts[0] not in SKIP]


def manifest(root, report_id):
    folder = store.report_dir(root, report_id)
    lines = [f"{sha256(p)}  report-{report_id}/{p.relative_to(folder).as_posix()}"
             for p in files(root, report_id)]
    return "\n".join(lines) + "\n"


# The Sphinx project

def heading(title, char="="):
    title = " ".join(title.split())
    return f"{title}\n{char * len(title)}\n"


def run_title(run):
    variation = (run.get("variation") or {}).get("name")
    parts = [run["script"], run.get("environment"), variation]
    return " / ".join(p for p in parts if p) + f" · run {run['id'][:8]}"


def project(root, report_id, out, target, base_url, exported, manifest_hash):
    """Write the Sphinx project for `target` ("html" or "latex") into `out`"""
    data = ReportData(root, report_id)
    template = report_template(root, report_id)
    out.mkdir(parents=True)
    (out / "runs").mkdir()
    for run in data.runs:
        (out / "runs" / f"{run['id']}.rst").write_text(
            heading(run_title(run))
            + f"\n.. run-summary::\n\n.. run-document:: {run['id']}\n")
    doc_source = source(root, report_id)
    failing = [r["latest"]["id"] for r in data.combinations
               if r["state"] in ("fail", "error") and r["latest"]]
    if target == "html":
        runs = "\n".join(f"   runs/{r['id']}" for r in data.runs)
        doc_source += f"\n\n.. toctree::\n   :hidden:\n   :caption: Runs\n\n{runs}\n" if runs else ""
        exclude = []
    else:  # the failing runs' documents, as appendices
        exclude = [f"runs/{r['id']}.rst" for r in data.runs if r["id"] not in failing]
        if failing:
            runs = "\n".join(f"   runs/{i}" for i in failing)
            doc_source += f"\n\n.. raw:: latex\n\n   \\appendix\n\n.. toctree::\n\n{runs}\n"
    title = f"{data.name}\n{'=' * len(data.name)}\n\n" if not doc_source.lstrip().startswith(
        data.name) else ""
    (out / "index.rst").write_text((title if target == "html" else "") + doc_source)
    document = data.document
    settings = template_settings(template)
    names = document["signatures"]
    roles = list(settings["roles"]) + [r for r in names if r not in settings["roles"]]
    from ...framework.plugins import plugin_css, plugin_latex
    static = out / "_plugins"
    static.mkdir()
    (static / "plugins.css").write_text(plugin_css())
    (out / "build.json").write_text(json.dumps({
        "title": data.name, "author": document["author"] or "",
        "root": str(Path(root).resolve()), "folder": report_id,
        "template": str(template), "snippets": str(template / "snippets"),
        "server_url": base_url, "exported": exported, "manifest_hash": manifest_hash,
        "exclude": exclude,
        "plugin_static": str(static),
        "latex_files": [str(p) for p in template.iterdir()
                        if p.is_file() and p.name not in LATEX_SKIP],
        "latex": {
            "company": latex(settings.get("company", "")),
            "marking": latex(settings.get("marking", "")),
            "document_type": latex(settings.get("document_type", "Test Report")),
            "title": latex(document["title"]),
            "number": latex(document["number"] or "-"),
            "revision": latex(document["revision"] or "-"),
            "author": latex(document["author"]),
            "date": latex(exported[:10]),
            "report_id": latex(data.id),
            "manifest_hash": latex(manifest_hash),
            "signatures": [(latex(role), latex(names.get(role, ""))) for role in roles],
            "applicable": numbered(document["documents"], "applicable", "AD"),
            "reference": numbered(document["documents"], "reference", "RD"),
            "plugins": plugin_latex(),
        },
    }, indent=2))
    (out / "conf.py").write_text(
        "from automationv3.services.reports.sphinx_conf import configure\n"
        "configure(globals(), __file__.replace('conf.py', 'build.json'))\n")
    return out


def sphinx(srcdir, outdir, builder, log):
    result = subprocess.run(
        [sys.executable, "-m", "sphinx", "-b", builder, "-q", "-E",
         "-d", str(outdir.parent / f"doctrees-{builder}"), str(srcdir), str(outdir)],
        capture_output=True, text=True)
    log.write(f"$ sphinx -b {builder}\n{result.stdout}{result.stderr}\n")
    if result.returncode != 0:
        raise ExportError(f"Sphinx couldn't build the {builder}: "
                          + (result.stderr.strip().splitlines() or ["(no output)"])[-1])


def build(root, report_id, base_url=""):
    """Build the report's site and PDF into build/, waiting for it.
    Returns the status; on a failure its "error" says why."""
    folder = build_dir(root, report_id)
    for name in ("site", "report.pdf", "report.tex"):
        path = folder / name
        shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink(
            missing_ok=True)
    exported = now_iso()
    from ...framework.plugins import plugin_versions
    set_status(root, report_id, state="building", started=exported, ended=None, error=None,
               framework=framework(), plugins=plugin_versions())
    manifest_text = manifest(root, report_id)
    (folder / "MANIFEST.sha256").write_text(manifest_text)
    manifest_hash = hashlib.sha256(manifest_text.encode()).hexdigest()
    with tempfile.TemporaryDirectory() as tmp, open(log_path(root, report_id), "w") as log:
        work = Path(tmp)
        try:
            html = project(root, report_id, work / "html", "html", base_url, exported,
                           manifest_hash)
            sphinx(html, work / "site", "html", log)
            shutil.copytree(work / "site", folder / "site")
            latex_src = project(root, report_id, work / "latex", "latex", base_url, exported,
                                manifest_hash)
            sphinx(latex_src, work / "pdf", "latex", log)
            build_pdf(work / "pdf")
            shutil.copy(work / "pdf" / "report.pdf", pdf_path(root, report_id))
            shutil.copy(work / "pdf" / "report.tex", folder / "report.tex")
        except Exception as e:
            log.write(f"\n{type(e).__name__}: {e}\n")
            return set_status(root, report_id, state="failed", ended=now_iso(),
                              error=str(e))
    return set_status(root, report_id, state="done", ended=now_iso(),
                      exported=exported, manifest_hash=manifest_hash)


def start(root, report_id, base_url=""):
    """Build the report in a process of its own; status() follows it"""
    set_status(root, report_id, state="building", started=now_iso(), ended=None,
               error=None)
    subprocess.Popen(
        [sys.executable, "-m", "automationv3.services.reports.build", str(root), report_id,
         base_url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def framework():
    """What built it: automation-v3's version (and git commit, when it
    runs from a checkout)"""
    from ..worker.host import framework_fingerprint
    try:
        return framework_fingerprint()
    except Exception:
        return {}


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
