"""A script's statements, rendered for reading

A script's statements are its document's parts: the prose between rvt
blocks (rst, rendered as written) and each form in its rvt blocks. A
form renders through its BuildingBlock, so blocks control how they look
(see BuildingBlock.as_rst / as_html); forms without a block show as
code.
"""

import functools

from . import document, edn
from .closure import is_definition
from .rst import repr_rst, write_html_parts


class Statement:
    """One statement: its edn form and its rst and html renderings.

    `in_definitions` is set for the forms of the script's definitions
    section (rvt blocks marked :definitions:), and `definition` for every
    def, defn or defblock; pages show these collapsed.
    """

    def __init__(self, statement, html=None, rst=None, in_definitions=False):
        self.statement = statement
        self.html = html or ""
        self.rst = rst or ""
        self.in_definitions = in_definitions
        self.definition = is_definition(statement)

    @property
    def defines(self):
        """The name a definition binds, else None"""
        return str(self.statement[1]) if self.definition else None

    def __str__(self):
        return edn.writes(self.statement).replace("\\n", "\n").strip('"')

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
    html = write_html_parts(rst)
    section = set(document.definitions_section(parts))
    return [
        Statement(form, h, r, index in section)
        for index, (form, h, r) in enumerate(zip(forms, html, rst))
    ]
