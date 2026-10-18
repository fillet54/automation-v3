"""Scripts as reStructuredText

Every statement becomes rst: prose as written, forms through their
BuildingBlock (see documents/script.py for a whole script as one
document). Scripts may reference requirements with the :req:`ID` role.
"""

import functools

import docutils.core
from docutils import nodes, utils
from docutils.parsers.rst import roles

from . import edn, markup
from .block import code_block, find_block
from .language import (
    PRECONDITION, head, is_table_rows, is_text, parse_precondition, parse_table,
    parse_variations,
)
from .requirement import SHALL, Requirement

# How a :req:`ID` reference finds its requirement. Applications with a
# requirements store install their own lookup; it may return None. Its
# key says what the lookup would answer from (the requirements' context
# and their latest import, say), so rendering cached under another key
# isn't reused.
_requirement_lookup = None
_requirement_key = None


def set_requirement_lookup(lookup, key=None):
    """Use `lookup(id) -> Requirement | None` to resolve :req: references,
    and `key() -> hashable` to tell apart what it would answer from"""
    global _requirement_lookup, _requirement_key
    _requirement_lookup = lookup
    _requirement_key = key


def requirement_key():
    return _requirement_key() if _requirement_key else None


def find_requirement(id):
    found = _requirement_lookup(id) if _requirement_lookup else None
    return found or Requirement(id)


@functools.lru_cache(maxsize=1024)
def _plain(text):
    try:
        return docutils.core.publish_doctree(text, settings_overrides={
            "report_level": 5, "halt_level": 5, "doctitle_xform": False}).astext()
    except Exception:
        return text


def requirement_nodes(req, rawtext=""):
    """A requirement as inline nodes: its text (plain), each "shall"
    marked with its id; just its id if its text isn't known"""
    node = nodes.inline(rawtext, classes=["ui-requirement", "requirement"])
    if not req.text:
        node += nodes.strong("", f"[{req.id}]", classes=["shall"])
        return node
    words = " ".join(_plain(req.text).split())
    parts = SHALL.split(f" {words} ")
    for n, part in enumerate(parts):
        if n % 2:
            node += nodes.strong("", f"{part} [{req.id}]", classes=["shall"])
        elif part.strip(" ") or 0 < n < len(parts) - 1:
            node += nodes.Text(part[1:] if n == 0 else part[:-1] if n == len(parts) - 1
                               else part)
    return node


def requirement_role(role, rawtext, text, lineno, inliner, options=None, content=None):
    return [requirement_nodes(find_requirement(utils.unescape(text)), rawtext)], []


roles.register_canonical_role("REQ", requirement_role)


def repr_rst(form):
    """A statement as rst: documentation as written, language forms
    (variations, Precondition) readably, steps through their block"""
    if is_text(form):
        return form
    if not isinstance(form, list) or not form:  # a bare value: shown as code
        return code_block(edn.writes(form))
    name = head(form)
    if name == "variations" and (table := variations_rst(form)):
        return table
    if is_table_rows(form) and (table := table_rst(form)):
        return table
    if name == PRECONDITION and parse_precondition(form):
        return precondition_rst(form)
    if block := find_block(form):
        return block.__repr_rst__()
    return code_block(edn.writes(form))


def variations_rst(form):
    """A variations form as a table, one row per variation"""
    errors = []
    variations = parse_variations("", form, errors)
    if errors or not variations:
        return None
    return markup.table(
        ["Variation", *variations[0].symbols],
        [[v.name, *v.forms] for v in variations],
        caption="Variations",
    )


def table_rst(form):
    """A table block's rows as a table, one row per case"""
    errors = []
    rows = parse_table("", form, errors)
    if errors or not rows:
        return None
    return markup.table(["Case", *rows[0].symbols], [[r.name, *r.forms] for r in rows],
                        caption="For each row")


def precondition_rst(form):
    """The precondition's name. Pages show its check and heal themselves,
    like a titled block's steps (see statements.Statement.precondition)."""
    return f"**Precondition:** {parse_precondition(form).name}"
