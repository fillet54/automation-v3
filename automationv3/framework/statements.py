"""A script's statements, rendered for reading

Each top-level form of a script is a statement. Documentation strings
are reStructuredText. A step renders through its BuildingBlock, so
blocks control how they look (see BuildingBlock.as_rst / as_html);
steps without a block show as code.
"""

import functools

from . import edn
from .rst import repr_rst, write_html_parts


class Statement:
    """One statement: its edn form and its rst and html renderings"""

    def __init__(self, statement, html=None, rst=None):
        self.statement = statement
        self.html = html or ""
        self.rst = rst or ""

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
    forms = list(edn.read_all(text))
    rst = [repr_rst(form) for form in forms]
    html = write_html_parts(rst)
    return [Statement(form, h, r) for form, h, r in zip(forms, html, rst)]
