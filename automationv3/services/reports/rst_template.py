"""Jinja templates that write reStructuredText

A line starting with ``%`` is a statement (``% for row in rows``), and one
starting with ``%#`` a comment; either is dropped whole, newline and all,
so the blank lines rst depends on come out exactly as written. (Not ``.``:
rst's own ``..`` would read as one. And not Jinja's built-in line
statements, which swallow the blank line after them.)

Every ``{{ value }}`` is escaped as plain text, so nothing in a value is
ever markup. Filters that write markup (``literal``, ``indent``, those a
template's caller adds) return Rst, which is written as it is.
"""

import re

import jinja2
from jinja2.ext import Extension


class Rst(str):
    """Text that is already reStructuredText"""


# Inline markup that could start anywhere: emphasis, literals,
# interpreted text and substitutions; and a reference's closing "_"
INLINE = re.compile(r"([\\`*|])|_(?=\W|$)")
# What could open a block at the start of a line: a bullet or
# enumerated list, a field, a comment or directive, a line block
BLOCK = re.compile(r"[-+*•|]( |$)|:|(\d+|[a-zA-Z#]|[ivxlcdmIVXLCDM]+)[.)]( |$)"
                   r"|\(\w+\)( |$)|\.\.( |$)|>>>")


def text(value):
    """`value` on one line, as plain rst text: nothing in it is markup"""
    value = " ".join(str(value if value is not None else "").split())
    value = INLINE.sub(lambda m: "\\" + m.group(0), value)
    if BLOCK.match(value) or (len(value) > 1 and len(set(value)) == 1
                              and not value[0].isalnum()):
        value = "\\" + value  # not a list, nor a heading's underline
    if value.endswith("::"):
        value = value[:-1] + "\\:"  # not the start of a literal block
    return Rst(value)


def literal(value):
    """`value` as inline literal text"""
    value = " ".join(str(value if value is not None else "").split())
    return Rst(f"``{value.replace('``', '` `')}``" if value else "")


def indent(value, width=3, first=False):
    """`value`'s lines indented by `width` (the first too, if `first`),
    blank lines left blank; escaped first unless it is Rst"""
    value = value if isinstance(value, Rst) else text(value)
    pad = " " * width
    lines = value.split("\n")
    return Rst("\n".join(
        (pad + line if line.strip() and (n or first) else line)
        for n, line in enumerate(lines)))


def verbatim(value, width=3):
    """`value` as it is, every line indented: for a literal block's body"""
    return indent(Rst(str(value if value is not None else "").rstrip() or "(empty)"),
                  width, first=True)


def heading(title, char):
    """A section title and its underline"""
    title = text(title)
    return Rst(f"{title}\n{char * len(title)}")


def escape(value):
    return value if isinstance(value, Rst) else text(value)


LINE = re.compile(r"^[ \t]*%(?:#.*|[ \t]+(.*?)[ \t]*)$\n?", re.MULTILINE)


class LineStatements(Extension):
    """``% statement`` lines become ``{% statement %}``, the whole line
    dropped; ``%#`` lines are dropped"""

    def preprocess(self, source, name, filename=None):
        return LINE.sub(lambda m: "{% " + m.group(1) + " %}" if m.group(1) else "", source)


def environment(loader):
    env = jinja2.Environment(
        loader=loader, extensions=[LineStatements], finalize=escape,
        autoescape=False, keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined)
    env.filters.update(text=text, literal=literal, indent=indent,
                       verbatim=verbatim, heading=heading, rst=Rst)
    return env
