"""Scripts as reStructuredText

Every statement becomes rst: prose as written, forms through their
BuildingBlock (see documents/script.py for a whole script as one
document). Scripts may reference requirements with the :req:`ID` role
(source.py reads it; RequirementReferences here writes it).
"""

import functools

import docutils.core
from docutils import nodes
from docutils.transforms import Transform

from . import edn, markup
from .block import code_block, find_block
from .language import (
    PRECONDITION, head, is_table_rows, is_text, parse_precondition, parse_table,
    parse_variations,
)
from .requirement import SHALL, Requirement
from .source import requirement_reference

@functools.lru_cache(maxsize=1024)
def plain_text(text):
    """A requirement's rst text as plain words, markup and line breaks
    gone"""
    try:
        tree = docutils.core.publish_doctree(text, settings_overrides={
            "report_level": 5, "halt_level": 5, "doctitle_xform": False,
            "file_insertion_enabled": False})
        return " ".join(tree.astext().split())
    except Exception:
        return " ".join(str(text).split())


def mark_shall(root, req_id, classes=("shall",)):
    """Mark every 'shall' in Text nodes under `root` with `req_id`"""
    for text_node in list(root.findall(nodes.Text)):
        if isinstance(text_node.parent, (nodes.literal, nodes.literal_block)):
            continue
        raw = str(text_node)
        parts = SHALL.split(f" {raw} ")
        if len(parts) == 1:
            continue
        replacement = []
        for n, part in enumerate(parts):
            if n % 2:
                strong = nodes.strong("", f"{part} [{req_id}]")
                if classes:
                    strong["classes"].extend(classes)
                replacement.append(strong)
            else:
                if n == 0:
                    part = part[1:]
                if n == len(parts) - 1:
                    part = part[:-1]
                if part:
                    replacement.append(nodes.Text(part))
        text_node.parent.replace(text_node, replacement)
    return root


def requirement_nodes(req, rawtext=""):
    """A requirement as inline nodes: its text (plain), each "shall"
    marked with its id; just its id if its text isn't known"""
    node = nodes.inline(rawtext, classes=["ui-requirement", "requirement"])
    if not req.text:
        node += nodes.strong("", f"[{req.id}]", classes=["shall"])
        return node
    node += nodes.Text(plain_text(req.text))
    return mark_shall(node, req.id)


class RequirementReferences(Transform):
    """Each :req: reference (a source.requirement_reference, which holds
    only the id) as the requirement's text, looked up now: rendering
    applies it, parsing never does (see documents/core.py and the
    reports' Sphinx extension)"""

    default_priority = 210

    def __init__(self, document, startnode=None, lookup=None):
        super().__init__(document, startnode=startnode)
        self.lookup = lookup

    def apply(self):
        lookup = self.lookup or getattr(self.document.settings, "requirement_lookup", None)
        for node in list(self.document.findall(requirement_reference)):
            found = lookup(node["id"]) if lookup else None
            req = found or Requirement(node["id"])
            node.replace_self(requirement_nodes(req, node.rawsource))


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
    like a titled block's steps (see documents/script.view)."""
    return f"**Precondition:** {parse_precondition(form).name}"
