"""Reading an export from the DOORS exporter

An export is a folder: manifest.json, and one Sphinx source tree per spec
it names (see docs/reference/requirements-export.rst). `read` checks it
all and returns each spec with its files, its requirements and their
content hashes; nothing here touches the database.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path

from . import rst_source

FORMAT = 1
LEVELS = ("system", "segment", "software")
TYPES = ("string", "enum", "list")
KEY = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_.-]*\Z")


class ExportError(ValueError):
    pass


def digest(value):
    """sha256 of bytes, or of a JSON value written canonically"""
    if not isinstance(value, bytes):
        value = json.dumps(value, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode()
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class Requirement:
    """A requirement in one spec version, with a hash per part of its
    content. `hash` is of everything stored (raw text and unhashed
    attributes too); the facet hashes decide what changed."""
    id: str
    text: str
    attributes: dict
    satisfies: tuple
    section: tuple
    text_hash: str
    metadata_hash: str
    links_hash: str
    section_hash: str
    hash: str


@dataclass
class Spec:
    """One spec of an export: trunk (baseline None) or a baseline"""
    key: str
    title: str
    level: str
    parents: list
    attributes: dict
    baseline: str = None
    doors: dict = field(default_factory=dict)
    files: dict = field(default_factory=dict)  # path -> bytes
    requirements: list = field(default_factory=list)

    @property
    def tree(self):
        """path -> sha256 of every file in the spec's source"""
        return {path: digest(content) for path, content in sorted(self.files.items())}

    @property
    def hash(self):
        """The spec version: its description, schema and source"""
        return digest({"key": self.key, "title": self.title, "level": self.level,
                       "parents": sorted(self.parents), "attributes": self.attributes,
                       "tree": self.tree})

    @property
    def label(self):
        return f"{self.key}@{self.baseline}" if self.baseline else f"{self.key} (trunk)"


@dataclass
class Export:
    path: Path
    manifest: dict
    specs: list
    baseline_sets: list  # [{"name", "specs": {key: baseline}}]
    exported_at: str = None  # UTC, "YYYY-MM-DDTHH:MM:SS.ffffffZ"


def exported_at(value):
    """manifest.json's exported_at, as UTC "YYYY-MM-DDTHH:MM:SS.ffffffZ"
    (so they compare as strings); None if it has none. Raises ExportError if it isn't ISO 8601 with a zone."""
    if value is None:
        return None
    try:
        when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ExportError(f"manifest.json: exported_at {value!r} is not an ISO 8601 time")
    if when.tzinfo is None:
        raise ExportError(f"manifest.json: exported_at {value!r} needs a time zone "
                          f"(end it in Z for UTC)")
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def read(path):
    """The Export in folder `path`. Raises ExportError naming every
    problem found."""
    path = Path(path)
    try:
        manifest = json.loads((path / "manifest.json").read_text())
    except FileNotFoundError:
        raise ExportError(f"{path}: no manifest.json")
    except json.JSONDecodeError as e:
        raise ExportError(f"{path}/manifest.json: {e}")
    problems = []
    if manifest.get("format") != FORMAT:
        raise ExportError(f"manifest.json: format {manifest.get('format')!r} is not "
                          f"one this version reads ({FORMAT})")
    specs, seen = [], set()
    for i, entry in enumerate(manifest.get("specs") or []):
        try:
            spec = read_spec(path, entry)
        except ExportError as e:
            problems.append(str(e))
            continue
        if (spec.key, spec.baseline) in seen:
            problems.append(f"{spec.label} is in the manifest twice")
        seen.add((spec.key, spec.baseline))
        specs.append(spec)
    sets = manifest.get("baseline_sets") or []
    if not specs and not sets and not problems:
        problems.append("manifest.json names no specs and no baseline sets")
    for s in sets:
        if not s.get("name") or not isinstance(s.get("specs"), dict) or not s["specs"]:
            problems.append(f"baseline set {s.get('name')!r} needs a name and specs")
    problems += duplicate_ids([s for s in specs if s.baseline is None])
    when = exported_at(manifest.get("exported_at"))
    if when is None and any(s.baseline is None for s in specs):
        problems.append("manifest.json: exported_at is needed to import trunk, "
                        "which only moves forward")
    if problems:
        raise ExportError("\n".join(problems))
    return Export(path, manifest, specs, sets, when)


def read_spec(path, entry):
    key = entry.get("key") or ""
    if not KEY.match(key):
        raise ExportError(f"spec key {key!r}: letters, digits, '-', '_' and '.' only")
    label = f"{key}@{entry['baseline']}" if entry.get("baseline") else key
    level = entry.get("level")
    if level not in LEVELS:
        raise ExportError(f"{label}: level {level!r} is not one of {', '.join(LEVELS)}")
    parents = entry.get("parents") or []
    if level == "system" and parents:
        raise ExportError(f"{label}: a system spec has no parents")
    attributes = check_schema(label, entry.get("attributes") or {})
    root = path / (entry.get("root") or key)
    if not (root / "index.rst").is_file():
        raise ExportError(f"{label}: {root}/index.rst is missing")
    files = {p.relative_to(root).as_posix(): p.read_bytes()
             for p in sorted(root.rglob("*")) if p.is_file()}
    if "conf.py" in files:
        raise ExportError(f"{label}: has a conf.py; automation supplies the configuration")
    spec = Spec(key=key, title=entry.get("title") or key, level=level,
                parents=sorted(parents), attributes=attributes,
                baseline=entry.get("baseline") or None, doors=entry.get("doors") or {},
                files=files)
    spec.requirements = spec_requirements(spec)
    return spec


def check_schema(label, attributes):
    """The schema with its defaults filled in"""
    out = {}
    for name, a in attributes.items():
        if name == "satisfies" or not KEY.match(name) or name != name.lower():
            raise ExportError(f"{label}: attribute {name!r} needs a lower-case name, "
                              f"not 'satisfies'")
        if a.get("type") not in TYPES:
            raise ExportError(f"{label}: attribute {name}: type {a.get('type')!r} is not "
                              f"one of {', '.join(TYPES)}")
        if a["type"] == "enum" and not a.get("values"):
            raise ExportError(f"{label}: attribute {name}: an enum needs values")
        out[name] = {"type": a["type"], "hashed": a.get("hashed", True) is not False,
                     **({"values": list(a["values"])} if a["type"] == "enum" else {})}
    return out


def spec_requirements(spec):
    """Every requirement in the spec's rst files, checked against its
    schema and hashed"""
    found, problems, seen = [], [], set()
    for path, content in spec.files.items():
        if not path.endswith(".rst"):
            continue
        try:
            parsed = rst_source.parse(content.decode("utf-8"), f"{spec.key}/{path}")
        except (rst_source.RequirementsError, UnicodeDecodeError) as e:
            problems.append(f"{spec.label}: {e}")
            continue
        for p in parsed:
            if p.id in seen:
                problems.append(f"{spec.label}: requirement {p.id} is defined twice")
                continue
            seen.add(p.id)
            try:
                found.append(hashed(p, spec.attributes))
            except ExportError as e:
                problems.append(f"{spec.label}: {p.id}: {e}")
    if problems:
        raise ExportError("\n".join(problems))
    return found


def attribute_value(name, value, schema):
    a = schema.get(name)
    if a is None:
        raise ExportError(f"attribute {name!r} is not in the spec's schema")
    if a["type"] == "list":
        return sorted({v.strip() for v in value.split(",") if v.strip()})
    if a["type"] == "enum" and value not in a["values"]:
        raise ExportError(f"{name}: {value!r} is not one of {', '.join(a['values'])}")
    return value


def hashed(p, schema):
    attributes = {name: attribute_value(name, value, schema)
                  for name, value in sorted(p.attributes.items())}
    text_hash = digest(rst_source.plain_text(p.text))
    metadata_hash = digest({k: v for k, v in attributes.items() if schema[k]["hashed"]})
    links_hash = digest(list(p.satisfies))
    section_hash = digest(list(p.section))
    return Requirement(
        id=p.id, text=p.text, attributes=attributes, satisfies=p.satisfies,
        section=p.section, text_hash=text_hash, metadata_hash=metadata_hash,
        links_hash=links_hash, section_hash=section_hash,
        hash=digest({"id": p.id, "text": p.text, "attributes": attributes,
                     "satisfies": list(p.satisfies), "section": list(p.section)}))


def duplicate_ids(specs):
    """Problems for ids in more than one of `specs`"""
    owner, problems = {}, []
    for spec in specs:
        for r in spec.requirements:
            if r.id in owner and owner[r.id] != spec.label:
                problems.append(f"requirement {r.id} is in both {owner[r.id]} and {spec.label}")
            owner.setdefault(r.id, spec.label)
    return problems
