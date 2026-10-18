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

import io
import re
from pathlib import Path

import jinja2
from docutils import nodes
from docutils.core import publish_doctree
from docutils.utils import SystemMessage
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
                       verbatim=verbatim, heading=heading, rst=Rst,
                       verdict=verdict, link=link, seconds=seconds, plural=plural,
                       stamp=stamp, requirement=requirement, **FILTERS)
    return env


FILTERS = {}  # more filters for every snippet: see `filter`


def filter(fn=None, name=None):
    """Make `fn` a filter every snippet can use (a decorator)"""
    if fn is None:
        return lambda f: filter(f, name)
    FILTERS[name or fn.__name__] = fn
    return fn


# Filters every snippet can use

def verdict(state):
    """A state (pass, fail, green, ...) as :verdict:, which every output
    can style by its class"""
    state = " ".join(str(state or "").split())
    return Rst(f":verdict:`{state.replace('`', '')}`") if state else Rst("")


def link(label, url, literal_label=False):
    """`label` linking to `url`, or just the label when there is none"""
    shown = literal(label) if literal_label else text(label)
    if not url or not shown:
        return shown
    if literal_label:  # a literal can't be a link's text: link plain text
        shown = text(label)
    return Rst(f"`{shown} <{url}>`__")


def seconds(value):
    if value is None:
        return ""
    return f"{value:.1f} s" if value < 600 else f"{value / 60:.1f} min"


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def stamp(iso):
    return iso.replace("T", " ").replace("+00:00", " UTC") if iso else ""


def requirement(value):
    """A requirement's text: as the rst it is, in a requirement container,
    when it stands on its own as body text; else as plain text"""
    if not value:
        return Rst("*text not recorded*")
    if not body_only(value):
        return text(value)
    return Rst(".. container:: requirement\n\n" + indent(Rst(value.strip()), 3, first=True))


def body_only(value):
    """Whether rst `value` parses cleanly with plain docutils, to nothing
    but body elements (no sections, which a table cell can't hold)"""
    problems = io.StringIO()
    try:
        tree = publish_doctree(value, settings_overrides={
            "warning_stream": problems, "report_level": 2, "halt_level": 2,
            "doctitle_xform": False, "file_insertion_enabled": False,
            "raw_enabled": False})
    except SystemMessage:
        return False
    return not problems.getvalue() and not any(
        tree.findall(lambda n: isinstance(n, (nodes.section, nodes.transition,
                                              nodes.title, nodes.target))))


# Snippets

BUILTIN = Path(__file__).parent / "snippets"


class Snippets:
    """Snippet templates by name ("report/results.rst"), looked up in
    `folders` in order, then in plugins' (see register_folder), then the
    built-in ones"""

    plugin_folders = []

    def __init__(self, folders=()):
        self.folders = [str(f) for f in folders if f and Path(f).is_dir()]
        self.env = environment(jinja2.FileSystemLoader(
            [*self.folders, *map(str, self.plugin_folders), str(BUILTIN)]))

    def render(self, name, **values):
        return Rst(self.env.get_template(name).render(**values))


def register_folder(folder):
    """Add a plugin's snippet folder, overriding the built-in snippets"""
    Snippets.plugin_folders.append(Path(folder))
