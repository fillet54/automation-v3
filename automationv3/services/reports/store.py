"""Filesystem store for reports and runs

Finished results are plain files. Each report is a uuidv7 folder and
each run is a uuidv7 folder inside its report::

    <root>/
      <report-id>/
        report.json
        runs/
          <run-id>/
            run.json
            closure/        exact files executed
            events.jsonl    observer events, one per line
            files/          files attached by observers

uuidv7 ids sort by creation time, so sorting run ids gives run order.
"""

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

_uuid7_lock = threading.Lock()
_uuid7_last = (0, 0)


def uuid7():
    """Time ordered UUID (RFC 9562 version 7), monotonic within a process"""
    global _uuid7_last
    with _uuid7_lock:
        ms = time.time_ns() // 1_000_000
        last_ms, last_seq = _uuid7_last
        if ms <= last_ms:
            # Same (or earlier) millisecond: bump the 12 bit sequence
            ms, seq = last_ms, last_seq + 1
            if seq > 0xFFF:
                ms, seq = ms + 1, 0
        else:
            seq = int.from_bytes(os.urandom(2), "big") & 0x7FF
        _uuid7_last = (ms, seq)

    rand_b = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)
    value = (ms & ((1 << 48) - 1)) << 80 | 0x7 << 76 | seq << 64 | 0b10 << 62 | rand_b
    return str(uuid.UUID(int=value))


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path, data):
    """Write atomically so readers never see a partial file"""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def _read_json(path):
    return json.loads(path.read_text())


def report_dir(root, report_id):
    return Path(root) / report_id


def run_dir(root, report_id, run_id):
    return report_dir(root, report_id) / "runs" / run_id


def create_report(root, **meta):
    report_id = uuid7()
    path = report_dir(root, report_id)
    (path / "runs").mkdir(parents=True)
    _write_json(path / "report.json", {"id": report_id, "created": now_iso(), **meta})
    return report_id


def create_run(root, report_id, script, closure):
    """Create a run folder holding the closure (relative path -> text)"""
    run_id = uuid7()
    path = run_dir(root, report_id, run_id)
    (path / "files").mkdir(parents=True)
    for relpath, text in closure.items():
        dest = path / "closure" / relpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
    (path / "events.jsonl").touch()
    _write_json(
        path / "run.json",
        {
            "id": run_id,
            "report_id": report_id,
            "script": script,
            "created": now_iso(),
            "outcome": None,
        },
    )
    return run_id


def save_file(root, report_id, run_id, name, data):
    """Store `data` (bytes) in the run's files/ folder under `name`, or a
    numbered variant of it if taken. Returns the name used."""
    folder = run_dir(root, report_id, run_id) / "files"
    folder.mkdir(exist_ok=True)
    name = Path(name).name.lstrip(".") or "file"
    stem, suffix = Path(name).stem, Path(name).suffix
    stored, n = name, 1
    while (folder / stored).exists():
        n += 1
        stored = f"{stem}-{n}{suffix}"
    (folder / stored).write_bytes(data)
    return stored


def list_files(root, report_id, run_id):
    """Names of the files attached to a run"""
    folder = run_dir(root, report_id, run_id) / "files"
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


def file_path(root, report_id, run_id, name):
    """The path of an attached file, or None if there is no such file"""
    path = run_dir(root, report_id, run_id) / "files" / Path(name).name
    return path if path.is_file() else None


def read_closure(root, report_id, run_id):
    base = run_dir(root, report_id, run_id) / "closure"
    return {
        str(p.relative_to(base)): p.read_text()
        for p in sorted(base.rglob("*"))
        if p.is_file()
    }


def append_events(root, report_id, run_id, events):
    path = run_dir(root, report_id, run_id) / "events.jsonl"
    with path.open("a") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")


def read_events(root, report_id, run_id):
    path = run_dir(root, report_id, run_id) / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def reset_run(root, report_id, run_id):
    """Forget a released probe: clear its events and start time"""
    path = run_dir(root, report_id, run_id)
    (path / "events.jsonl").write_text("")
    run = _read_json(path / "run.json")
    run.pop("started", None)
    run["probes"] = run.get("probes", 0) + 1
    _write_json(path / "run.json", run)


def update_run(root, report_id, run_id, **fields):
    path = run_dir(root, report_id, run_id) / "run.json"
    run = _read_json(path)
    run.update(fields)
    _write_json(path, run)
    return run


def load_run(root, report_id, run_id):
    path = run_dir(root, report_id, run_id) / "run.json"
    return _read_json(path) if path.exists() else None


def load_report(root, report_id):
    path = report_dir(root, report_id) / "report.json"
    return _read_json(path) if path.exists() else None


def list_runs(root, report_id):
    """Runs of a report, oldest first"""
    runs = report_dir(root, report_id) / "runs"
    if not runs.is_dir():
        return []
    return [
        _read_json(p / "run.json")
        for p in sorted(runs.iterdir())
        if (p / "run.json").exists()
    ]


def list_reports(root):
    """All reports, newest first"""
    root = Path(root)
    if not root.is_dir():
        return []
    return [
        _read_json(p / "report.json")
        for p in sorted(root.iterdir(), reverse=True)
        if (p / "report.json").exists()
    ]
