"""What the old script reader gave, kept to compare the new one with

Used only while plans/source-tree.md is carried out, and deleted at its
end. `python -m test.baseline` writes test/baseline.json from the code
as it is: for every .rst file git tracks, the cards `cards.split` cuts,
and for every script (a file with an rvt block) the parts
`document.parse` gives, each form with its options, title, table marks
and every span inside it. test/test_baseline.py compares today's code
with the file; steps 2 and 3 point it at the new code.

The demo's scripts are copies of test/data/rvts, so they add nothing.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "test" / "baseline.json"


def files():
    """Every .rst file git tracks, relative to the repository, in order"""
    listed = subprocess.check_output(["git", "ls-files", "*.rst"], cwd=ROOT, text=True)
    return sorted(listed.split())


def span(value):
    """A span as [line, col, end_line, end_col], or None"""
    return None if value is None else list(value[:4])


def spans(form):
    """Every span inside `form`, in the order move_spans visits them"""
    from automationv3.framework import edn

    found = [span(edn.span_of(form))]
    inner = getattr(form, "spans", None)
    if isinstance(inner, list):
        found.append([span(s) for s in inner])
    elif isinstance(inner, dict):
        found.append([[span(a), span(b)] for a, b in inner.values()])
    if isinstance(form, dict):
        for key, value in form.items():
            found += [spans(key), spans(value)]
    elif isinstance(form, (list, set)):
        found += [spans(item) for item in form]
    return found


def options(values):
    return {name: list(value) if isinstance(value, list) else value
            for name, value in sorted(values.items())}


def part(found):
    """One part, as plain data"""
    from automationv3.framework import edn

    if found.prose:
        return {"prose": found.form, "line": found.line}
    return {"form": edn.writes(found.form), "line": found.line, "title": found.title,
            "options": options(found.options), "table": found.table,
            "table_rows": found.table_rows, "span": span(found.span),
            "spans": spans(found.form)}


def card(found):
    """One card and its children, as plain data; its source as its line
    count, which is where it was cut"""
    return {"kind": found.kind, "line": found.line, "index": found.index,
            "lines": found.source.count("\n"), "text": found.text,
            "heading": found.heading, "level": found.level, "title": found.title,
            "definitions": found.definitions, "table": found.table,
            "variations": list(found.variations), "code": found.code,
            "code_line": found.code_line, "code_indent": found.code_indent,
            "indent": found.indent, "count": found.count,
            "children": [card(child) for child in found.children]}


def record(path, text):
    """What today's code makes of one file"""
    from automationv3.framework import cards, document

    entry = {"cards": [card(c) for c in cards.split(text)]}
    if document.has_rvt(text):
        try:
            entry["parts"] = [part(p) for p in document.parse(text, path=path)]
        except Exception as error:  # noqa: BLE001  what failed is the record
            entry["error"] = f"{type(error).__name__}: {error}"
    return entry


def snapshot():
    return {path: record(path, (ROOT / path).read_text()) for path in files()}


def load():
    return json.loads(SNAPSHOT.read_text())


def main():
    data = snapshot()
    lines = [f"{json.dumps(path)}: {json.dumps(entry, ensure_ascii=False)}"
             for path, entry in data.items()]  # a file a line
    SNAPSHOT.write_text("{\n" + ",\n".join(lines) + "\n}\n")
    scripts = sum("parts" in entry or "error" in entry for entry in data.values())
    print(f"{SNAPSHOT.relative_to(ROOT)}: {len(data)} files, {scripts} scripts", file=sys.stderr)


if __name__ == "__main__":
    main()
