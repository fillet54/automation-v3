"""Rendering scripts through reStructuredText

Every statement becomes rst (documentation as written, steps through
their BuildingBlock), the whole script is rendered to HTML in one pass,
and the HTML is split back into one part per statement. Scripts may
reference requirements with the :req:`ID` role.
"""

import docutils.core
from docutils import nodes
from docutils.parsers.rst import roles, Directive, directives
from docutils.writers.html4css1 import Writer, HTMLTranslator

from . import edn, html
from .block import find_block, raw_html
from .closure import PRECONDITION, head, parse_precondition, parse_variations
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


def requirement_reference_role(
    role, rawtext, text, lineno, inliner, options=None, content=None
):
    """rst role to support software requirement references"""
    try:
        node = requirement(text)
        return [node], []
    except Exception as e:
        print(e)
    return [], []


class requirement(nodes.Inline, nodes.TextElement):
    def __init__(self, id):
        super().__init__()
        self.req = find_requirement(id)


# Register requirement role
roles.register_canonical_role("REQ", requirement_reference_role)


class endstatement(nodes.Inline, nodes.TextElement):
    pass


class EndStatement(Directive):
    """This `Directive` will split up statements"""

    required_arguments = 0
    optional_arguments = 0
    has_content = False

    def run(self):
        thenode = endstatement()
        return [thenode]


directives.register_directive("endstatement", EndStatement)


class RvtDirective(Directive):
    """`.. rvt::` marks how the script uses the forms that follow, e.g.
    `:definitions:`. It renders nothing; pages group the forms instead."""

    required_arguments = 0
    optional_arguments = 0
    has_content = False
    option_spec = {"definitions": directives.flag}

    def run(self):
        return []


directives.register_directive("rvt", RvtDirective)


class TestcaseHTMLTranslator(HTMLTranslator):
    documenttag_args = {
        "tagname": "div",
        "CLASS": "document prose prose-li:mt-0 prose-li:mb-0 prose-p:mb-1 prose-p:mt-1 prose-headings:mb-2 prose-headings:mt-5",  # noqa: E501
    }

    # Delimiters for endstatement directives
    ENDSTATEMENT_RST = "\n\n.. endstatement::\n\n"
    ENDSTATEMENT_DIV = '<splitter id="1234567890!!!!"/>'

    def __init__(self, document):
        HTMLTranslator.__init__(self, document)

    def visit_document(self, node):
        super().visit_document(node)
        self.body.append(self.ENDSTATEMENT_DIV)

    def depart_document(self, node):
        self.body.append(self.ENDSTATEMENT_DIV)
        super().depart_document(node)

    # Don't want nested sections since we might split
    # a section
    def visit_section(self, node):
        pass

    def depart_section(self, node):
        pass

    def visit_endstatement(self, node):
        self.body.append(self.ENDSTATEMENT_DIV)

    def depart_endstatement(self, node):
        pass

    def visit_requirement(self, node):
        return self.body.append(node.req.__repr_html__())

    def depart_requirement(self, node):
        pass


class TestcaseHTMLWriter(Writer):
    def __init__(self, requirement_by_id=None):
        Writer.__init__(self)
        self.translator_class = TestcaseHTMLTranslator


def rst_codeblock(src):
    return (
        "\n".join(
            [".. code-block:: clojure", "", *["  " + line for line in src.splitlines()]]
        )
        + "\n\n"
    )


def repr_rst(form):
    """A statement as rst: documentation as written, language forms
    (variations, Precondition) readably, steps through their block"""
    if isinstance(form, str):
        return form
    name = head(form)
    if name == "variations" and (table := variations_html(form)):
        return raw_html(table)
    if name == PRECONDITION and parse_precondition(form):
        return precondition_rst(form)
    if block := find_block(form):
        return block.__repr_rst__()
    return rst_codeblock(edn.writes(form))


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
    """The precondition's name, then its check and heal as they render"""
    name, check, heal = parse_precondition(form)
    rst = f"**Precondition:** {name}\n\n{repr_rst(check)}"
    if heal is not None:
        rst += f"\n\n*If not, heal by:*\n\n{repr_rst(heal)}"
    return rst


def write_html_parts(rst_statements):
    # At this point we can assume all of our statements
    # are in rst format. To allow us to split up the rendered
    # html we need to insert some marker so we can split on
    # that after. To do this we will use a custom rst
    # directive.
    rst_text = TestcaseHTMLTranslator.ENDSTATEMENT_RST.join(rst_statements)
    html = docutils.core.publish_parts(
        rst_text,
        writer=TestcaseHTMLWriter(),
        settings_overrides={"initial_header_level": "3"},
    )

    # Now we should be able to split the HTML on
    # our custom div pattern. Throw away the first
    # and last as thats the wrapping 'document' divs
    return html["html_body"].split(TestcaseHTMLTranslator.ENDSTATEMENT_DIV)[1:-1]
