"""Rendering scripts through reStructuredText

Every statement becomes rst (prose as written, forms through their
BuildingBlock), the whole script is rendered to HTML in one pass, and
the HTML is split back into one part per statement. Scripts may
reference requirements with the :req:`ID` role.
"""

import docutils.core
from docutils import nodes
from docutils.parsers.rst import roles, Directive, directives
from docutils.writers.html4css1 import Writer, HTMLTranslator

from . import edn, html
from .block import code_block, find_block, raw_html
from .language import PRECONDITION, head, is_text, parse_precondition, parse_variations
from .requirement import Requirement

# How a :req:`ID` reference finds its requirement. Applications with a
# requirements store install their own lookup; it may return None.
_requirement_lookup = None


def set_requirement_lookup(lookup):
    """Use `lookup(id) -> Requirement | None` to resolve :req: references"""
    global _requirement_lookup
    _requirement_lookup = lookup


def find_requirement(id):
    found = _requirement_lookup(id) if _requirement_lookup else None
    return found or Requirement(id)


class requirement(nodes.Inline, nodes.TextElement):
    """A :req:`ID` reference, rendered by its Requirement"""

    def __init__(self, id):
        super().__init__()
        self.req = find_requirement(id)


def requirement_role(role, rawtext, text, lineno, inliner, options=None, content=None):
    return [requirement(text)], []


roles.register_canonical_role("REQ", requirement_role)


class endstatement(nodes.Inline, nodes.TextElement):
    """Where one statement's rendering ends and the next one's begins"""


class EndStatement(Directive):
    def run(self):
        return [endstatement()]


directives.register_directive("endstatement", EndStatement)

# The endstatement directive between statements, and what it renders as
ENDSTATEMENT_RST = "\n\n.. endstatement::\n\n"
ENDSTATEMENT_HTML = '<splitter id="1234567890!!!!"/>'


class StatementsTranslator(HTMLTranslator):
    """HTML with a splitter at each statement boundary, the start and the
    end of the document, and no section wrappers (a statement may end
    inside a section)"""

    def visit_document(self, node):
        super().visit_document(node)
        self.body.append(ENDSTATEMENT_HTML)

    def depart_document(self, node):
        self.body.append(ENDSTATEMENT_HTML)
        super().depart_document(node)

    def visit_section(self, node):
        pass

    def depart_section(self, node):
        pass

    def visit_endstatement(self, node):
        self.body.append(ENDSTATEMENT_HTML)

    def depart_endstatement(self, node):
        pass

    def visit_requirement(self, node):
        self.body.append(node.req.__repr_html__())

    def depart_requirement(self, node):
        pass


class StatementsWriter(Writer):
    def __init__(self):
        super().__init__()
        self.translator_class = StatementsTranslator


def repr_rst(form):
    """A statement as rst: documentation as written, language forms
    (variations, Precondition) readably, steps through their block"""
    if is_text(form):
        return form
    if not isinstance(form, list) or not form:  # a bare value: shown as code
        return code_block(edn.writes(form))
    name = head(form)
    if name == "variations" and (table := variations_html(form)):
        return raw_html(table)
    if name == PRECONDITION and parse_precondition(form):
        return precondition_rst(form)
    if block := find_block(form):
        return block.__repr_rst__()
    return code_block(edn.writes(form))


def variations_html(form):
    """A variations form as a table, one row per variation"""
    errors = []
    variations = parse_variations("", form, errors)
    if errors or not variations:
        return None
    return html.table(
        ["Variation", *variations[0].symbols],
        [[v.name, *v.forms] for v in variations],
        caption="Variations",
    )


def precondition_rst(form):
    """The precondition's name. Pages show its check and heal themselves,
    like a titled block's steps (see statements.Statement.precondition)."""
    return f"**Precondition:** {parse_precondition(form).name}"


def write_html_parts(rst_statements):
    """Each rst statement as HTML, rendered as one document so headings,
    lists and references carry across statements"""
    html = docutils.core.publish_parts(
        ENDSTATEMENT_RST.join(rst_statements),
        writer=StatementsWriter(),
        settings_overrides={"initial_header_level": "3"},
    )
    # Splitters wrap the document too: drop what's before the first and
    # after the last
    return html["html_body"].split(ENDSTATEMENT_HTML)[1:-1]
