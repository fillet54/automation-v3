"""Spreadsheets on their way in: held between upload and import, so the
Imports page can ask which column is which and show what would change

An upload is kept in a folder of its own under the staging root, named
by a random token, until it is imported or a day has passed. Nothing in
the database changes until the import.
"""

import json
import re
import secrets
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePath

from . import models, store

KEEP_SECONDS = 24 * 3600
TOKEN = re.compile(r"\A[A-Za-z0-9_-]{8,64}\Z")


def stage(root, data, name):
    """Keep an upload's bytes; returns its token"""
    root = Path(root)
    clean(root)
    token = secrets.token_urlsafe(12)
    folder = root / token
    folder.mkdir(parents=True)
    (folder / "name").write_text(PurePath(name).name or "upload", encoding="utf-8")
    (folder / "data").write_bytes(data)
    return token


def load(root, token):
    """(bytes, file name) of a staged upload, or None"""
    if not TOKEN.match(token or ""):
        return None
    folder = Path(root) / token
    try:
        return (folder / "data").read_bytes(), (folder / "name").read_text(encoding="utf-8")
    except OSError:
        return None


def drop(root, token):
    if TOKEN.match(token or ""):
        shutil.rmtree(Path(root) / token, ignore_errors=True)


def clean(root, now=None):
    """Forget uploads older than KEEP_SECONDS"""
    now = now or time.time()
    if not Path(root).is_dir():
        return
    for folder in Path(root).iterdir():
        try:
            if now - folder.stat().st_mtime > KEEP_SECONDS:
                shutil.rmtree(folder, ignore_errors=True)
        except OSError:
            pass


def remembered(conn, file_name):
    """How the newest import of a file named `file_name` was read: {spec,
    title, level, parents, sheet, columns}, or None"""
    for (manifest,) in conn.execute("SELECT manifest FROM imports ORDER BY id DESC"):
        try:
            manifest = json.loads(manifest)
        except ValueError:
            continue
        if (manifest.get("exporter") or {}).get("name") != "flat":
            continue
        for entry in manifest.get("specs") or []:
            source = entry.get("source") or {}
            if source.get("file") == file_name:
                return {"spec": entry.get("key"), "title": entry.get("title"),
                        "level": entry.get("level"), "parents": entry.get("parents") or [],
                        "sheet": source.get("sheet"), "columns": source.get("columns")}
    return None


@dataclass
class Preview:
    """What importing a flat file's spec would do, against what is there
    now: trunk, or the baseline of the same name"""
    label: str
    against: str = None  # the context compared with; None if the spec is new
    added: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    changed: list = field(default_factory=list)  # (before, after)
    unchanged: int = 0
    refused: str = None  # why the import would be refused

    @property
    def changes(self):
        return bool(self.added or self.removed or self.changed)


def as_requirement(spec, r):
    """A framework Requirement for one of an export.Spec's requirements"""
    return models.build_requirement(spec, r.id, r.text, r.attributes, r.satisfies, r.section,
                                    version=r.hash, text_hash=r.text_hash)


def _hashed_facets(r):
    return {
        "text_hash": r.text_hash,
        "metadata_hash": r.metadata_hash,
        "links_hash": r.links_hash,
        "section_hash": r.section_hash,
    }


def preview(conn, found):
    """The Preview of importing `found`, a flat file's one-spec Export"""
    (spec,) = found.specs
    out = Preview(spec.label)
    context = f"{spec.key}@{spec.baseline}" if spec.baseline else "trunk"
    try:
        resolved = models.resolve(conn, context)
        known = spec.key in resolved
    except models.ContextError:
        resolved, known = {}, False  # a new baseline
    if spec.baseline and not known:
        resolved = models.resolve(conn, "trunk")
        context, known = ("trunk", True) if spec.key in resolved else (context, False)
    incoming = [(r, as_requirement(spec.key, r)) for r in spec.requirements]
    if not known:
        out.added = [req for _, req in incoming]
        return out
    out.against = context
    current_rows = store.contents(conn, resolved[spec.key])
    for raw, req in incoming:
        before_row = current_rows.pop(req.id, None)
        if before_row is None:
            out.added.append(req)
        elif not store.facet_changes(before_row, _hashed_facets(raw)):
            out.unchanged += 1
        else:
            out.changed.append((models.as_requirement(spec.key, before_row), req))
    out.removed = [models.as_requirement(spec.key, row) for row in current_rows.values()]
    if spec.baseline and context != "trunk" and out.changes:
        out.refused = (f"{spec.label} is already imported with other content: a baseline "
                       "never changes. Import it as a new baseline, or as trunk")
    return out
