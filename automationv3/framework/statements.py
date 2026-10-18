"""A script's statements, rendered for reading

A script's statements are its document's parts: the prose between rvt
blocks (rst, rendered as written) and each form in its rvt blocks. A
form renders through its BuildingBlock, so blocks control how they look
(see BuildingBlock.as_rst); forms without a block show as
code.
"""

import functools

from . import document, edn, rst
from .language import PRECONDITION, head, is_definition, is_text, parse_precondition
from .rst import repr_rst


class Statement:
    """One statement: its edn form and how it reads, as rst.

    `in_definitions` is set for the forms of the script's definitions
    section (rvt blocks marked :definitions:), and `definition` for every
    def or defn; pages show these collapsed. `variations` is
    the names its block is limited to, else None (every variation);
    `block` is where its rvt block starts (None for prose) and `title`
    that block's title, if it has one. A Precondition's `precondition`
    holds its name, its heal's description and its check and heal as
    rst on their own, for pages that show it like a titled block.
    """

    def __init__(self, statement, rst=None, in_definitions=False,
                 variations=None, block=None, title=None):
        self.statement = statement
        self.rst = rst or ""
        self.in_definitions = in_definitions
        self.definition = is_definition(statement)
        self.variations = variations
        self.block = block
        self.title = title
        self.precondition = None
        self.span = None  # where the form is in the script (an edn.Span)
        self.table = None  # the line of its :table: block, if in one
        self.table_rows = False  # the table block's rows

    @property
    def defines(self):
        """The name a definition binds, else None"""
        return str(self.statement[1]) if self.definition else None

    def __str__(self):
        return self.statement if is_text(self.statement) else edn.writes(self.statement)

    def __repr__(self):
        return str(self)

    def _repr_rst_(self):
        return self.rst


def get_statements(text):
    """The script's statements, rendered"""
    return _statements(text, rst.requirement_key())


# Pages ask for the same script repeatedly, so cache by content. Its
# :req: references read the requirements' text, so the cache is by what
# that text comes from too.
@functools.lru_cache(maxsize=128)
def _statements(text, requirement_key):
    parts = document.parse(text)
    section = set(document.definitions_section(parts))
    statements = []
    for index, part in enumerate(parts):
        statement = Statement(part.form, repr_rst(part.form), index in section,
                              part.variations, None if part.prose else part.line,
                              part.title)
        statement.span = part.span
        statement.table = part.table
        statement.table_rows = part.table_rows
        parsed = head(part.form) == PRECONDITION and parse_precondition(part.form)
        if parsed:
            statement.precondition = {
                "name": parsed.name,
                "heal_name": parsed.heal_name,
                "check_rst": repr_rst(parsed.check),
                "heal_rst": repr_rst(parsed.heal) if parsed.heal is not None else None,
            }
        statements.append(statement)
    return statements


get_statements.cache_clear = _statements.cache_clear
