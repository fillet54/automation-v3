"""Requirements from a flat file: a spreadsheet, or a list, one per line

For projects without specs written in rst. A flat file holds one spec;
reading it gives an export.Export like an export folder's, so it imports
the same way (history, changes, baselines, suspects).

A spreadsheet (CSV, TSV, or an Excel workbook's sheet) has a header row.
Columns gives each column its role: the id and the text are needed; the
ids it satisfies and a section (a heading to group under) are optional;
other columns are attributes, or ignored. Without Columns, the roles are
guessed from the headers (`guess`)::

    id,text,satisfies,subsystem
    SRS-001,The VM shall shed loads below 40%.,SYS-12,EPS

A list has one requirement per line, its id and then its text::

    SRS-001  The VM shall shed loads below 40%.
    SRS-002: The VM shall report the state of charge.

Blank lines, and lines starting with #, are skipped.

The text is plain: characters rst would read as markup (``*``, a
leading ``-``) are escaped, so it shows and hashes as written.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import PurePath

from . import export
from .export import ExportError

SHEET_SUFFIXES = (".csv", ".tsv", ".xlsx")
LIST_SUFFIXES = (".txt", ".list")
FLAT_SUFFIXES = SHEET_SUFFIXES + LIST_SUFFIXES
ID = re.compile(r"\A[^\s,;]+\Z")
SPECIAL = re.compile(r"([^\w\s]|_)")
ROLES = ("id", "text", "satisfies", "section")

# Headers each role is guessed from, normalized (see `normal`)
SYNONYMS = {
    "id": {"id", "req id", "requirement id", "identifier", "object identifier", "key",
           "req", "req no", "requirement number", "number", "absolute number", "tag"},
    "text": {"text", "requirement", "requirement text", "requirements", "description",
             "object text", "statement", "shall", "req text"},
    "satisfies": {"satisfies", "parent", "parents", "parent id", "parent ids",
                  "parent requirement", "parent requirements", "traces to", "trace",
                  "traces", "satisfied requirements", "links", "in links"},
    "section": {"section", "heading", "chapter", "group", "category"},
}


def is_flat(name):
    """True if file `name` is read as a flat file (by its suffix)"""
    return PurePath(str(name)).suffix.lower() in FLAT_SUFFIXES


def is_sheet(name):
    return PurePath(str(name)).suffix.lower() in SHEET_SUFFIXES


@dataclass
class Table:
    """A spreadsheet's header row and the rows below it: (row number,
    [cell text]); and, for a workbook, its sheets and which one this is"""
    headers: list
    rows: list
    sheets: list = field(default_factory=list)
    sheet: str = None


@dataclass
class Columns:
    """Each column's role, by index into the header row: id, text,
    satisfies and section (None if no column), and attributes, index ->
    attribute name. Columns in none of these are ignored."""
    id: int = None
    text: int = None
    satisfies: int = None
    section: int = None
    attributes: dict = field(default_factory=dict)

    def by_header(self, headers):
        """These Columns by header, to keep: {role: header, "attributes":
        {header: name}}"""
        found = {role: headers[i] for role in ROLES
                 if (i := getattr(self, role)) is not None}
        found["attributes"] = {headers[i]: name for i, name in self.attributes.items()}
        return found

    @classmethod
    def from_headers(cls, saved, headers):
        """Columns kept by `by_header`, for a table with `headers`; roles
        whose header is no longer there are dropped"""
        where = {h: i for i, h in enumerate(headers)}
        roles = {role: where.get(saved.get(role)) for role in ROLES}
        attributes = {where[h]: name for h, name in (saved.get("attributes") or {}).items()
                      if h in where and where[h] not in roles.values()}
        return cls(**roles, attributes=attributes)


def normal(header):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(header).lower()).split())


def attribute_name(header):
    """A header as an attribute name: lower case, '-' between words"""
    return "-".join(normal(header).split())


def guess(headers):
    """Columns for `headers`: each role from the first header that names
    it (see SYNONYMS), and every other named column as an attribute"""
    found = Columns()
    for i, header in enumerate(headers):
        role = next((r for r in ROLES if normal(header) in SYNONYMS[r]), None)
        if role and getattr(found, role) is None:
            setattr(found, role, i)
    taken = {getattr(found, r) for r in ROLES}
    names = set()
    for i, header in enumerate(headers):
        name = attribute_name(header)
        if i in taken or not name or name in ROLES or name in names:
            continue
        names.add(name)
        found.attributes[i] = name
    return found


def cell(value):
    """A spreadsheet cell's value as text"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == datetime.min.time() \
            else value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def table(data, name, sheet=None):
    """The Table in spreadsheet `name` (its bytes): for a workbook, sheet
    `sheet` (default: the first with anything on it). Raises ExportError."""
    suffix = PurePath(name).suffix.lower()
    if suffix == ".xlsx":
        return workbook_table(data, name, sheet)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ExportError(f"{name} isn't UTF-8 text: save it as UTF-8 "
                          "(in Excel, CSV UTF-8), or upload the workbook (.xlsx)") from None
    reader = csv.reader(io.StringIO(text), delimiter="\t" if suffix == ".tsv" else ",")
    rows = []
    for values in reader:
        rows.append((reader.line_num, values))
    return header_table(rows, name)


def workbook_table(data, name, sheet=None):
    import openpyxl  # here, so starting the app doesn't load it

    try:
        book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:
        raise ExportError(f"{name} can't be read as an Excel workbook ({e})") from None
    try:
        sheets = [ws.title for ws in book.worksheets if ws.sheet_state == "visible"] \
            or book.sheetnames
        if sheet is not None and sheet not in book.sheetnames:
            raise ExportError(f"{name} has no sheet {sheet!r} "
                              f"(it has {', '.join(sheets)})")

        def read_rows(title):
            return [(n, [cell(v) for v in values]) for n, values
                    in enumerate(book[title].iter_rows(values_only=True), start=1)]

        # By default, the first sheet with anything on it (not a blank cover)
        for chosen in [sheet] if sheet else sheets:
            rows = read_rows(chosen)
            if any(any(v.strip() for v in values) for _, values in rows):
                break
        else:
            chosen = sheet or sheets[0]
    finally:
        book.close()
    found = header_table(rows, name)
    found.sheets, found.sheet = sheets, chosen
    return found


def header_table(rows, name):
    """A Table from (row number, values): the first row with anything in
    it is the header row, and blank rows are dropped"""
    rows = [(n, [v.strip() if isinstance(v, str) else v for v in values])
            for n, values in rows]
    rows = [(n, values) for n, values in rows if any(values)]
    if not rows:
        raise ExportError(f"{name} is empty: it needs a header row, then a row "
                          "per requirement")
    (_, headers), body = rows[0], rows[1:]
    while headers and not headers[-1]:
        headers = headers[:-1]
    width = max([len(headers)] + [len(v) for _, v in body])
    headers = headers + [""] * (width - len(headers))
    return Table(headers, [(n, values + [""] * (width - len(values))) for n, values in body])


def read(data, name, spec, baseline=None, title=None, level="software", parents=(),
         columns=None, sheet=None):
    """The Export of flat file `name` (its bytes), as spec `spec`. A
    spreadsheet's columns are `columns` (Columns), or guessed. Raises
    ExportError naming every problem found."""
    check_spec(name, spec, level, parents)
    suffix = PurePath(name).suffix.lower()
    if suffix in SHEET_SUFFIXES:
        found = table(data, name, sheet)
        columns = columns or guess(found.headers)
        rows, attributes = sheet_rows(found, columns, name)
        source = {"sheet": found.sheet, "columns": columns.by_header(found.headers)}
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ExportError(f"{name} isn't UTF-8 text: save it as UTF-8") from None
        rows, attributes, source = list_rows(text, name), [], {}
    return as_export(name, rows, attributes, spec, baseline, title, level, parents,
                     {"file": PurePath(name).name, "format": suffix.lstrip("."),
                      **{k: v for k, v in source.items() if v is not None}})


def check_spec(name, spec, level, parents):
    if not spec or not export.KEY.match(spec):
        raise ExportError(f"{name}: name the spec it is, e.g. SRS "
                          f"(letters, digits, '-', '_' and '.')")
    if level not in export.LEVELS:
        raise ExportError(f"{name}: level {level!r} is not one of {', '.join(export.LEVELS)}")
    if level == "system" and any(p and p.strip() for p in parents):
        raise ExportError(f"{name}: a system spec has no parents")


def as_export(name, rows, attributes, spec, baseline, title, level, parents, source):
    parents = sorted({p.strip() for p in parents if p and p.strip()})
    entry = {"key": spec, "title": title or spec, "level": level, "parents": parents,
             "baseline": baseline or None, "source": source,
             "attributes": {c: {"type": "string"} for c in attributes}}
    s = export.Spec(key=spec, title=entry["title"], level=level, parents=parents,
                    attributes=export.check_schema(spec, entry["attributes"]),
                    baseline=entry["baseline"], doors={},
                    files={"index.rst": document(entry["title"], rows).encode()})
    try:
        s.requirements = export.spec_requirements(s)
    except ExportError as e:
        raise ExportError(f"{name}: {e}") from None
    manifest = {"format": export.FORMAT, "exporter": {"name": "flat"},
                "exported_at": now(), "specs": [entry]}
    return export.Export(name, manifest, [s], [], export.exported_at(manifest["exported_at"]))


def now():
    return datetime.now(timezone.utc).isoformat()


def check_columns(found, columns, name):
    """Problems with `columns` for Table `found`"""
    problems = []
    headers = found.headers
    for role in ("id", "text"):
        if getattr(columns, role) is None:
            named = ", ".join(h for h in headers if h) or "nothing"
            problems.append(f"{name}: which column holds each requirement's {role}? "
                            f"(the header row has {named})")
    used = [getattr(columns, r) for r in ROLES if getattr(columns, r) is not None]
    used += list(columns.attributes)
    for i in used:
        if not 0 <= i < len(headers):
            problems.append(f"{name}: there is no column {i + 1}")
    if len(set(used)) != len(used):
        problems.append(f"{name}: a column can have only one role")
    names = list(columns.attributes.values())
    for i, attribute in columns.attributes.items():
        if not attribute or not export.KEY.match(attribute) or attribute != attribute.lower():
            problems.append(f"{name}: column {i + 1} ({headers[i] if i < len(headers) else '?'})"
                            f": attribute name {attribute!r}: lower-case letters, digits, "
                            "'-', '_' and '.' only")
        elif attribute in ROLES:
            problems.append(f"{name}: an attribute can't be named {attribute!r}")
        elif names.count(attribute) > 1:
            problems.append(f"{name}: two columns are attribute {attribute!r}")
    return sorted(set(problems), key=problems.index)


def sheet_rows(found, columns, name):
    """([{line, id, text, satisfies, section, attributes}], attribute
    names) from a Table, by `columns`"""
    problems = check_columns(found, columns, name)
    if problems:
        raise ExportError("\n".join(problems))

    def get(values, i):
        return values[i] if i is not None else ""

    rows = []
    for line, values in found.rows:
        rows.append({"line": line, "id": get(values, columns.id).strip(),
                     "text": get(values, columns.text),
                     "satisfies": ", ".join(re.split(r"[\s,;]+",
                                                     get(values, columns.satisfies).strip()))
                     if get(values, columns.satisfies).strip() else "",
                     "section": " ".join(get(values, columns.section).split()),
                     "attributes": {name: values[i] for i, name in columns.attributes.items()}})
    problems = check_rows(rows, name)
    if not rows:
        problems.append(f"{name} has a header row but no requirements below it")
    if problems:
        raise ExportError("\n".join(problems))
    return rows, list(columns.attributes.values())


def list_rows(text, name):
    rows = []
    for line, content in enumerate(text.splitlines(), start=1):
        content = content.strip()
        if not content or content.startswith("#"):
            continue
        id, *rest = content.split(None, 1)
        rows.append({"line": line, "id": id.rstrip(":"), "text": "".join(rest).strip(),
                     "satisfies": "", "section": "", "attributes": {}})
    problems = check_rows(rows, name)
    if problems:
        raise ExportError("\n".join(problems))
    if not rows:
        raise ExportError(f"{name} holds no requirements")
    return rows


def check_rows(rows, name):
    problems, seen = [], {}
    for row in rows:
        where = f"{name}:{row['line']}"
        if not row["id"]:
            problems.append(f"{where}: no id")
        elif not ID.match(row["id"]):
            problems.append(f"{where}: id {row['id']!r} can't have spaces or commas")
        elif row["id"] in seen:
            problems.append(f"{where}: {row['id']} is also on line {seen[row['id']]}")
        else:
            seen[row["id"]] = row["line"]
        if not row["text"].strip():
            problems.append(f"{where}: {row['id'] or 'the requirement'} has no text")
        for target in row["satisfies"].split(","):
            if target.strip() and not ID.match(target.strip()):
                problems.append(f"{where}: satisfies {target.strip()!r}: "
                                "ids, separated by commas")
    return problems


def escape(text):
    """Plain text as rst that reads as the same text: markup characters
    escaped, paragraphs kept, indentation dropped"""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    return "\n\n".join(
        "\n".join(SPECIAL.sub(r"\\\1", line.strip())
                  for line in p.splitlines() if line.strip())
        for p in paragraphs)


def heading(title, mark):
    return [title, mark * max(len(title), 1), ""]


def document(title, rows):
    """The spec's index.rst: its title, then each section's
    requirements, in the order the sections first appear"""
    lines = heading(escape(title), "=")
    sections = {"": []}  # requirements in no section come before any heading
    for row in rows:
        sections.setdefault(row["section"], []).append(row)
    for section, members in sections.items():
        if section:
            lines += heading(escape(section), "-")
        for row in members:
            lines.append(f".. requirement:: {row['id']}")
            links = ", ".join(t.strip() for t in row["satisfies"].split(",") if t.strip())
            if links:
                lines.append(f"   :satisfies: {links}")
            for attribute, value in row["attributes"].items():
                value = " ".join(value.split())
                if value:
                    lines.append(f"   :{attribute}: {value}")
            lines.append("")
            lines += ["   " + line if line else "" for line in escape(row["text"]).splitlines()]
            lines.append("")
    return "\n".join(lines)
