"""A script's statements, rendered for reading

A script's statements, for its page, are the prose between rvt blocks
(rst, rendered as written) and each form in its rvt blocks. A
form renders through its BuildingBlock, so blocks control how they look
(see BuildingBlock.as_rst); forms without a block show as
code.
"""

import functools

from . import edn, source
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
        self.index = None  # its place among the script's forms; None for prose
        self.line = None  # where it starts in the file (a form: its block)

    @property
    def defines(self):
        """The name a definition binds, else None"""
        return str(self.statement[1]) if self.definition else None

    def __str__(self):
        return self.statement if is_text(self.statement) else edn.writes(self.statement)

    def __repr__(self):
        return str(self)

# Pages ask for the same script repeatedly, so cache by content. Its
# :req: references stay references until a page is rendered.
@functools.lru_cache(maxsize=128)
def get_statements(text):
    """The script's statements, rendered"""
    tree = source.parse(text)
    problems = source.unreadable(tree)
    if problems:
        raise ValueError(problems[0].message)
    return parts(tree)



def parts(tree):
    """The prose between rvt blocks and each of their forms, in file
    order, as Statements. A form's `index` is its place among the
    script's forms (source.statements); prose has none. Until the
    renderer reads the tree itself (step 5 of plans/source-tree.md)."""
    forms = {id(s.form): s for s in source.statements(tree)}
    return _parts(tree, tree.lines, 1, None, forms)


def _parts(container, lines, first, variations, forms):
    """The parts of `container` (the tree or an rvt-variant), whose
    `lines` start at file line `first`. Prose runs from the start, or
    from the first line after a directive that isn't blank, up to the
    next directive."""
    found, start = [], 0
    for block in source.blocks(container):
        _prose(found, lines[start:block["line"] - first], first + start, variations)
        if isinstance(block, source.rvt_variant):
            found += _parts(block, block["content"].splitlines(), block["content_line"] or 1,
                            block["variations"], forms)
        else:
            found += [_form(forms[id(form)]) for form, _ in block["forms"]]
        start = block["end"] - first + 1
        while start < len(lines) and not lines[start].strip():
            start += 1
    _prose(found, lines[start:], first + start, variations)
    return found


def _prose(found, lines, line, variations):
    text = "\n".join(lines)
    if text.strip():
        prose = Statement(text.strip("\n"), text.strip("\n"), False, variations, None)
        prose.line = line
        found.append(prose)


def _form(statement):
    form = statement.form
    found = Statement(form, repr_rst(form), statement.definitions, statement.variations,
                      statement.line, statement.title)
    found.index = statement.index
    found.line = statement.line
    found.span = statement.span
    found.table = statement.table
    found.table_rows = statement.table_rows
    parsed = head(form) == PRECONDITION and parse_precondition(form)
    if parsed:
        found.precondition = {
            "name": parsed.name,
            "heal_name": parsed.heal_name,
            "check_rst": repr_rst(parsed.check),
            "heal_rst": repr_rst(parsed.heal) if parsed.heal is not None else None,
        }
    return found
