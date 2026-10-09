"""A script's statements, rendered for reading

A script's statements are its document's parts: the prose between rvt
blocks (rst, rendered as written) and each form in its rvt blocks. A
form renders through its BuildingBlock, so blocks control how they look
(see BuildingBlock.as_rst / as_html); forms without a block show as
code.
"""

import functools

from . import document, edn
from .language import PRECONDITION, head, is_definition, is_text, parse_precondition
from .rst import repr_rst, write_html_parts


class Statement:
    """One statement: its edn form and its rst and html renderings.

    `in_definitions` is set for the forms of the script's definitions
    section (rvt blocks marked :definitions:), and `definition` for every
    def or defn; pages show these collapsed. `variations` is
    the names its block is limited to, else None (every variation);
    `block` is where its rvt block starts (None for prose) and `title`
    that block's title, if it has one. A Precondition's `precondition`
    holds its name, its heal's description and its check and heal
    rendered on their own, for pages that show it like a titled block.
    """

    def __init__(self, statement, html=None, rst=None, in_definitions=False,
                 variations=None, block=None, title=None):
        self.statement = statement
        self.html = html or ""
        self.rst = rst or ""
        self.in_definitions = in_definitions
        self.definition = is_definition(statement)
        self.variations = variations
        self.block = block
        self.title = title
        self.precondition = None
        self.span = None  # where the form is in the script (an edn.Span)

    @property
    def defines(self):
        """The name a definition binds, else None"""
        return str(self.statement[1]) if self.definition else None

    def __str__(self):
        return self.statement if is_text(self.statement) else edn.writes(self.statement)

    def __repr__(self):
        return str(self)

    def _repr_html_(self):
        return self.html

    def _repr_rst_(self):
        return self.rst


# Rendering runs docutils over the whole script, so cache by content:
# pages ask for the same script repeatedly.
@functools.lru_cache(maxsize=128)
def get_statements(text):
    parts = document.parse(text)
    forms = [part.form for part in parts]
    rst = [repr_rst(form) for form in forms]
    # A precondition's check and heal render with the rest, in one pass
    pieces = []
    for index, form in enumerate(forms):
        parsed = head(form) == PRECONDITION and parse_precondition(form)
        if parsed:
            pieces.append((index, parsed, repr_rst(parsed.check),
                           repr_rst(parsed.heal) if parsed.heal is not None else ""))
    rendered = write_html_parts(rst + [r for *_, check, heal in pieces
                                       for r in (check, heal)])
    html, extra = rendered[:len(rst)], rendered[len(rst):]
    section = set(document.definitions_section(parts))
    statements = [
        Statement(part.form, h, r, index in section, part.variations,
                  None if part.prose else part.line, part.title)
        for index, (part, h, r) in enumerate(zip(parts, html, rst))
    ]
    for statement, part in zip(statements, parts):
        statement.span = part.span
    for n, (index, parsed, _, _) in enumerate(pieces):
        statements[index].precondition = {
            "name": parsed.name,
            "heal_name": parsed.heal_name,
            "check_html": extra[2 * n],
            "heal_html": extra[2 * n + 1] if parsed.heal is not None else None,
        }
    return statements
