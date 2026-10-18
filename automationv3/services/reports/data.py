"""A report's data, read-only: what its documents are rendered from

Everything here comes from the report folder (report.json, and each run's
run.json, closure/, events.jsonl and files/), so the same object reads a
live report on the server or the copy in an exported bundle. Directives,
snippets and plugins read reports through it, never through the files.

`status(run)` names the state of a run that has no outcome yet (live
pages ask the job queue; a build says "unfinished"). `links` builds the
URLs a document links to (see Links).
"""

import functools
from datetime import datetime

from ...framework.statements import get_statements
from . import rollup, store

KINDS = ("applicable", "reference")
UNASSIGNED = "Unassigned"


def unfinished(run):
    return "unfinished"


class Links:
    """Where a document's links go. Live pages and exported sites link
    differently, so each builds its own; this one links nowhere."""

    def run(self, report_id, run_id):
        return None

    def requirement(self, id, snapshot):
        return None

    def file(self, report_id, run_id, name):
        return None


class ReportData:
    def __init__(self, root, report_id, status=unfinished, links=None):
        self.root, self.id = root, report_id
        self.status = status
        self.links = links or Links()
        self.report = store.load_report(root, report_id)
        if self.report is None:
            raise LookupError(f"No report {report_id} in {root}")

    # The report

    @property
    def name(self):
        return self.report.get("name") or f"Report {self.id[:8]}"

    @property
    def frozen(self):
        return store.is_frozen(self.report)

    @property
    def document(self):
        """The document's fields, with defaults for any not set. The
        document's title is the report's name."""
        fields = dict(self.report.get("document") or {})
        return {
            "title": self.name,
            "number": fields.get("number") or "",
            "revision": fields.get("revision") or "",
            "author": fields.get("author") or "",
            "signatures": dict(fields.get("signatures") or {}),
            "documents": [d for d in fields.get("documents") or [] if d.get("kind") in KINDS],
        }

    @property
    def snapshots(self):
        """id -> what the report kept of each requirement it tests"""
        return self.report.get("requirement_snapshots") or {}

    @property
    def uut_versions(self):
        return self.report.get("uut_versions") or {}

    # Runs

    @functools.cached_property
    def runs(self):
        """Every run, oldest first"""
        return store.list_runs(self.root, self.id)

    def run(self, run_id):
        return next((r for r in self.runs if r["id"] == run_id), None)

    def events(self, run):
        return store.read_events(self.root, self.id, run["id"])

    def closure(self, run):
        """relative path -> text of the files the run executed"""
        return store.read_closure(self.root, self.id, run["id"])

    def script_text(self, run):
        return store.read_closure_file(self.root, self.id, run["id"], run["script"]) or ""

    def files(self, run):
        return store.list_files(self.root, self.id, run["id"])

    def file_path(self, run, name):
        return store.file_path(self.root, self.id, run["id"], name)

    def statements(self, run):
        return get_statements(self.script_text(run))

    def state(self, run):
        return rollup.state_of(run, self.status, self.report)

    @property
    def first_run(self):
        started = [r["started"] for r in self.runs if r.get("started")]
        return min(started) if started else None

    @property
    def last_run(self):
        ended = [r["ended"] for r in self.runs if r.get("ended")]
        return max(ended) if ended else None

    @property
    def in_progress(self):
        return any(r.get("outcome") is None for r in self.runs)

    def environments(self):
        """environment -> the platforms its runs reported"""
        found = {}
        for run in self.runs:
            fingerprint = run.get("fingerprint") or {}
            platforms = found.setdefault(run.get("environment") or "", set())
            if fingerprint.get("platform"):
                platforms.add(fingerprint["platform"])
        return {env: sorted(p) for env, p in sorted(found.items())}

    def used_uut_versions(self):
        """name -> version, for the UUTs the runs used"""
        used = rollup.used_uuts(self.runs)
        return {name: v for name, v in self.uut_versions.items() if name in used}

    # The rollup

    @functools.cached_property
    def combinations(self):
        """Every combination of script, environment and variation, judged
        on its latest run (see rollup.combinations), with its attempts,
        duration and, if it failed, where and why"""
        rows = rollup.combinations(self.report, self.runs, self.status)
        for row in rows:
            row["attempts"] = len(row["earlier"]) + (1 if row["latest"] else 0)
            row["duration"] = duration(row["latest"])
            row["failure"] = (self.failure(row["latest"])
                              if row["state"] in ("fail", "error") else None)
            row["name"] = combination_name(row)
        return rows

    @functools.cached_property
    def requirements(self):
        """Each tracked requirement: its color, its combinations, and what
        the report kept of it (text, subsystem, where it links)"""
        entries = rollup.requirement_rollup(self.report, self.combinations)
        for entry in entries:
            snapshot = self.snapshots.get(entry["id"]) or {}
            entry["snapshot"] = snapshot
            entry["text"] = snapshot.get("text", "")
            entry["subsystem"] = snapshot.get("subsystem") or UNASSIGNED
            entry["spec"] = snapshot.get("spec")
            entry["url"] = self.links.requirement(entry["id"], snapshot)
            entry["scripts"] = self.report.get("requirements", {}).get(entry["id"], [])
        return entries

    def failure(self, run):
        """{"step", "message"} for a failed run: its first failed step (by
        title, where its block has one) and why"""
        events = self.events(run)
        for event in events:
            if event.get("kind") == "error":
                return {"step": "", "message": event.get("message", "")}
        failed = next((e for e in events if e.get("kind") == "step_end"
                       and not e.get("passed")), None)
        if failed is None:
            return {"step": "", "message": ""}
        message = failed.get("message") or failed.get("stderr") or failed.get("stdout") or ""
        return {"step": self.step_name(run, failed), "message": message.strip()}

    def step_name(self, run, ended):
        if ended.get("precondition"):
            return "Precondition"
        index = ended.get("index")
        statements = []
        if run["script"].endswith(".rst"):  # older runs were of .rvt scripts
            try:
                statements = self.statements(run)
            except Exception:
                pass
        name = f"step {index + 1}" if isinstance(index, int) else "a step"
        if isinstance(index, int) and index < len(statements) and statements[index].title:
            name = f"{statements[index].title} ({name})"
        if ended.get("row") is not None:
            name += f", row {ended['row']}"
        return name


def duration(run):
    if not run or not run.get("started") or not run.get("ended"):
        return None
    start, end = (datetime.fromisoformat(run[k]) for k in ("started", "ended"))
    return (end - start).total_seconds()


def combination_name(row):
    return " / ".join(p for p in (row["script"], row["environment"], row["variation"]) if p)
