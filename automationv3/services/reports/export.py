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
see the built-in one) and the files it includes, such as logo.pdf. A
workspace keeps its own in a report/ folder beside its rvts/ folder;
without one, the built-in template is used.
"""

import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import jinja2
from docutils.core import publish_parts
from docutils.utils import SystemMessage

from ...framework.statements import get_statements
from . import rollup, store

BUILTIN_TEMPLATE = Path(__file__).parent / "template"
EXPORTS = "exports"  # a report folder's exported bundles; never bundled
KINDS = ("applicable", "reference")


class ExportError(Exception):
    pass


# The report's document fields

def document_fields(report):
    """The report's document fields, with defaults for any not set. The
    document's title is the report's name."""
    fields = dict(report.get("document") or {})
    return {
        "title": report.get("name") or fields.get("title") or f"Report {report['id'][:8]}",
        "number": fields.get("number") or "",
        "revision": fields.get("revision") or "",
        "author": fields.get("author") or "",
        "signatures": dict(fields.get("signatures") or {}),
        "documents": [d for d in fields.get("documents") or [] if d.get("kind") in KINDS],
    }


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
    report = store.load_report(root, report_id)
    if report is None:
        raise ExportError(f"No report {report_id} in {root}")
    runs = store.list_runs(root, report_id)
    rows = rollup.combinations(report, runs, lambda run: "unfinished")
    requirements = rollup.requirement_rollup(report, rows)
    texts = report.get("requirement_texts") or {}
    for requirement in requirements:
        requirement["text"] = texts.get(requirement["id"], "")
    for row in rows:
        row["attempts"] = len(row["earlier"]) + (1 if row["latest"] else 0)
        row["duration"] = duration(row["latest"])
        row["failure"] = failure(root, row["latest"]) if row["state"] in (
            "fail", "error") else None
    started = [r["started"] for r in runs if r.get("started")]
    ended = [r["ended"] for r in runs if r.get("ended")]
    return {
        "report": report,
        "document": document_fields(report),
        "rows": rows,
        "requirements": requirements,
        "runs": runs,
        "first_run": min(started) if started else None,
        "last_run": max(ended) if ended else None,
        "environments": environments(runs),
    }


def duration(run):
    if not run or not run.get("started") or not run.get("ended"):
        return None
    start, end = (datetime.fromisoformat(run[k]) for k in ("started", "ended"))
    return (end - start).total_seconds()


def failure(root, run):
    """{"step", "message"} for a failed run: its first failed step (by
    title, where its block has one) and why"""
    events = store.read_events(root, run["report_id"], run["id"])
    for event in events:
        if event.get("kind") == "error":
            return {"step": "", "message": event.get("message", "")}
    failed = next((e for e in events if e.get("kind") == "step_end"
                   and not e.get("passed")), None)
    if failed is None:
        return {"step": "", "message": ""}
    message = failed.get("message") or failed.get("stderr") or failed.get("stdout") or ""
    return {"step": step_name(root, run, failed), "message": message.strip()}


def step_name(root, run, ended):
    if ended.get("precondition"):
        return "Precondition"
    index = ended.get("index")
    statements = []
    if run["script"].endswith(".rst"):  # older runs were of .rvt scripts
        text = store.read_closure(root, run["report_id"], run["id"]).get(run["script"], "")
        try:
            statements = get_statements(text)
        except Exception:
            pass
    name = f"step {index + 1}" if isinstance(index, int) else "a step"
    if isinstance(index, int) and index < len(statements) and statements[index].title:
        name = f"{statements[index].title} ({name})"
    if ended.get("row") is not None:
        name += f", row {ended['row']}"
    return name


def environments(runs):
    """environment -> the platforms its runs reported"""
    found = {}
    for run in runs:
        fingerprint = run.get("fingerprint") or {}
        platforms = found.setdefault(run.get("environment") or "", set())
        if fingerprint.get("platform"):
            platforms.add(fingerprint["platform"])
    return {env: sorted(p) for env, p in sorted(found.items())}


# The body, as reStructuredText

SPECIAL = re.compile(r"([\\`*_|\[\]<>:])")


def text(value):
    """`value` as plain rst text: nothing in it is markup"""
    value = " ".join(str(value if value is not None else "").split())
    value = SPECIAL.sub(r"\\\1", value)
    return "\\" + value if value[:1] in "-+#=.0123456789" and value else value


def literal(value):
    value = " ".join(str(value).split()).replace("``", "` `")
    return f"``{value}``" if value else ""


def table(caption, widths, header, rows):
    if not rows:
        return "None.\n"
    lines = [f".. list-table:: {text(caption)}", "   :header-rows: 1",
             f"   :widths: {' '.join(str(w) for w in widths)}", ""]
    for row in [header, *rows]:
        for n, cell in enumerate(row):
            first, *more = (cell or "\\-").split("\n")
            lines.append(f"   {'* -' if n == 0 else '  -'} {first}")
            lines += [f"       {line}" if line else "" for line in more]
    return "\n".join(lines) + "\n"


def heading(title, char):
    return f"{title}\n{char * len(title)}\n"


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


def render_rst(m, manifest_hash, exported):
    report, rows, requirements = m["report"], m["rows"], m["requirements"]
    out = []

    out.append(heading("Identification", "="))
    used = rollup.used_uuts(m["runs"])
    versions = ", ".join(f"{name} {v['id']} ({v.get('digest', '')[:12]})"
                         for name, v in (report.get("uut_versions") or {}).items()
                         if name in used)
    envs = "; ".join(f"{env or 'none'}: {', '.join(p) or 'platform not recorded'}"
                     for env, p in m["environments"].items())
    out.append(table("Report", [25, 75], ["Item", "Value"], [
        ["Report", literal(report["id"])],
        ["Name", text(report.get("name", ""))],
        ["Workspace", text(report.get("workspace", ""))],
        ["Created", text(stamp(report.get("created")))],
        ["Runs", text(f"{len(m['runs'])}, from {stamp(m['first_run']) or '-'} "
                      f"to {stamp(m['last_run']) or '-'}")],
        ["UUT versions", text(versions)],
        ["Environments", text(envs)],
        ["Exported", text(stamp(exported))],
        ["Bundle", literal(f"report-{report['id']}.zip")],
        ["Manifest SHA-256", literal(manifest_hash)],
    ]))

    out.append(heading("Summary", "="))
    colors = [r["color"] for r in requirements]
    states = [r["state"] for r in rows]
    summary = [[text(f"Requirements {c}"), text(colors.count(c))]
               for c in ("green", "red", "partial", "untested") if requirements]
    summary += [[text(f"Combinations {s}"), text(states.count(s))]
                for s in dict.fromkeys(["pass", "fail", "error", "incomplete",
                                        *states])]
    out.append(f"The report covers {plural(len(requirements), 'requirement')} with "
               f"{plural(len(rows), 'combination')} of script, environment and variation. "
               "Each combination is judged on its latest run; a requirement is "
               "green when every combination linked to it passed, red when any "
               "failed, untested when no script references it yet, and partial "
               "otherwise.\n")
    out.append(table("Summary", [70, 30], ["Item", "Count"], summary))

    out.append(heading("Open issues", "="))
    issues = [r for r in rows if r["state"] != "pass"]
    untested = [r for r in requirements if r["color"] == "untested"]
    if not issues and not untested:
        out.append("None: the latest run of every combination passed.\n")
    for requirement in untested:
        out.append(f"- {literal(requirement['id'])}: "
                   f"{text('untested: no script references it yet')}")
    for row in issues:
        detail = row["state"]
        if row["failure"]:
            if row["failure"]["step"]:
                detail += f" at {row['failure']['step']}"
            if row["failure"]["message"]:
                detail += f": {row['failure']['message']}"
        elif row["state"] == "incomplete":
            detail += ": steps are still to be written (TBD)"
        elif row["state"] == "outdated":
            ran = ", ".join(f"{n} {v}" for n, v in sorted(row["outdated"].items()))
            detail += f": {row['latest'].get('outcome')} on {ran}, not the report's versions"
        out.append(f"- {literal(combination(row))}: {text(detail)}")
    out.append("")

    out.append(heading("Requirements", "="))
    if not requirements:
        out.append("The report tracks no requirements.\n")
    else:
        out.append(table("Requirements", [15, 40, 9, 36],
                         ["Requirement", "Text", "Verdict", "Covered by"],
                         [[literal(r["id"]),
                           text(r["text"]) or "*text not recorded*",
                           f"**{text(r['color'])}**",
                           "\n".join(f"| {text(combination(c))}: {text(c['state'])}"
                                     for c in r["cells"]) or "*no tests yet*"]
                          for r in requirements]))

    out.append(heading("Results", "="))
    out.append("The latest run of each combination of script, environment and "
               "variation; earlier attempts are listed under Reruns. Run ids name "
               "the run's folder "
               f"under ``report-{report['id']}/runs/``.\n")
    out.append(table("Results", [27, 43, 19, 11],
                     ["Combination", "Run", "Outcome", "Duration"],
                     [[text(combination(r)),
                       literal((r["latest"] or {}).get("id", "")),
                       f"**{text(r['state'])}**"
                       + (f", {plural(r['attempts'], 'attempt')}" if r["attempts"] > 1
                          else ""),
                       text(seconds(r["duration"]))]
                      for r in rows]))
    earlier = [r for r in rows if r["earlier"]]
    if earlier:
        out.append(heading("Reruns", "-"))
        out.append("Earlier attempts of each combination, newest first.\n")
        for row in earlier:
            out.append(f"- {text(combination(row))}:\n")
            for run in row["earlier"]:
                out.append(f"  - {literal(run['id'])}: "
                           f"{text(run.get('outcome') or 'unfinished')}")
            out.append("")
        out.append("")

    failures = [r for r in rows if r["failure"]]
    if failures:
        out.append(heading("Failures", "-"))
        for row in failures:
            run_id = row["latest"]["id"]
            out.append(heading(combination(row), "~"))
            out.append(f"Run {literal(run_id)}, **{text(row['state'])}**"
                       + (f" at {text(row['failure']['step'])}"
                          if row["failure"]["step"] else "") + ".\n")
            if row["failure"]["message"]:
                out.append("::\n")
                for line in row["failure"]["message"].splitlines() or [""]:
                    out.append(f"   {line}")
                out.append("")
            out.append("Its events and attached files are in the report folder's "
                       f"{literal(f'runs/{run_id}/')}.\n")

    out.append(heading("Bundle", "="))
    out.append(f"This document describes the bundle report-{report['id']}.zip. "
               f"Its folder report-{report['id']} holds the report: "
               "``report.json``, and for each run ``run.json``, the exact files it "
               "executed (``closure/``), every event it recorded "
               "(``events.jsonl``) and the files attached to it (``files/``). "
               "``template/`` is the template this document was rendered with. "
               "``MANIFEST.sha256`` lists a SHA-256 for each of those files; its own "
               f"SHA-256 is {literal(manifest_hash)}.\n")
    return "\n".join(out)


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
        manifest_text = manifest(work, [report_name, "template"])
        (work / "MANIFEST.sha256").write_text(manifest_text)
        manifest_hash = hashlib.sha256(manifest_text.encode()).hexdigest()

        rst = render_rst(m, manifest_hash, exported)
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


def export(root, report_id, out_dir=None, template=None, requirement_texts=None):
    """Freeze the report and write its bundle; returns the zip's path.
    `out_dir` defaults to the report's exports/ folder. `requirement_texts`
    (id -> text) fills in requirement texts the report didn't record.

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
    was_frozen, texts = store.is_frozen(report), report.get("requirement_texts") or {}
    added = {k: v for k, v in (requirement_texts or {}).items()
             if k in report.get("requirements", {}) and not texts.get(k)}
    store.update_report(root, report_id, frozen=True,
                        requirement_texts={**texts, **added})
    try:
        return bundle(root, report_id, template,
                      out_dir or store.report_dir(root, report_id) / EXPORTS)
    except Exception:
        store.update_report(root, report_id, frozen=was_frozen, requirement_texts=texts)
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
