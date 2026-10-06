"""Script documents: reStructuredText with rvt blocks

A script (and a core.rst) is an ordinary reStructuredText document. Its
code lives in `rvt` directives whose content is edn forms::

    Steps
    -----

    .. rvt::
       :definitions:

       (def stop-pressure 70)

    .. rvt::

       (Wait 1)
       (Verify (reading :brake-pressure) <= stop-pressure)

    .. rvt::
       :variations: degraded, limp-home

       (Verify (reading :brake-pressure) <= limp-pressure)

A block marked `:variations:` (variation names, separated by commas)
only applies when one of those variations runs; a block without it
applies to every variation.

Prose and rvt blocks that belong to some variations only can be
wrapped together in an `rvt-variant` directive, whose content is split
like a document of its own and limited to its `:variations:`::

    .. rvt-variant::
       :variations: emergency

       In emergency mode the pressure stays at the limit.

       .. rvt::

          (Verify (reading :brake-pressure) = max-pressure)

An rvt block inside one may narrow it with `:variations:` of its own,
naming some of the variant's.

A block may have a title, which says what its forms do as a step of
the procedure; pages show a titled block collapsed to its title::

    .. rvt:: Apply the brakes fully

       (set-reading :brake-pressure max-pressure)
       (Verify (reading :brake-pressure) = max-pressure)

The document is split at its rvt directives. The prose between them
stays rst; each rvt directive is parsed by docutils (so its options are
read properly) and its content read as edn. A document's parts are the
prose chunks and the forms, in order: each prose chunk is a plain
string, each form carries its block's options.
"""

import re
from dataclasses import dataclass, field

import docutils.core
from docutils import nodes
from docutils.parsers.rst import Directive, directives

from . import edn
from .language import is_text

RVT_START = re.compile(r"^\.\. rvt::(\s.*)?$")
VARIANT_START = re.compile(r"^\.\. rvt-variant::\s*$")
ANY_RVT = re.compile(r"^\s*\.\. rvt::(\s.*)?$")


def variation_names(argument):
    """The names of a `:variations:` option, as a list"""
    names = [name.strip() for name in (argument or "").split(",")]
    if not all(names):
        raise ValueError("expected variation names separated by commas")
    return names


RVT_OPTIONS = {"definitions": directives.flag, "variations": variation_names}


@dataclass
class Part:
    """A prose chunk (str) or one form of an rvt block"""

    form: object
    options: dict = field(default_factory=dict)
    line: int = 0  # where the chunk or block starts, 1-based
    title: str = None  # the block's title, if it has one

    @property
    def variations(self):
        """The variation names this part is limited to, else None (all)"""
        return self.options.get("variations")

    def applies(self, variation):
        """True if the part runs for `variation` (None: no variation)"""
        if variation is None or self.variations is None:
            return True
        return variation in self.variations

    @property
    def prose(self):
        return is_text(self.form)


def split(text):
    """Chunks of (kind, source, line): "prose", "rvt" and "variant"
    (rvt-variant) directives, in order.

    A directive runs from its `.. rvt::` (or `.. rvt-variant::`) line
    through every indented or blank line after it.
    """
    chunks, current, start = [], [], 1
    kind = "prose"
    for line_no, line in enumerate(text.splitlines(), start=1):
        if kind != "prose" and line.strip() and not line[0].isspace():
            chunks.append((kind, "\n".join(current), start))
            current, start, kind = [], line_no, "prose"
        if kind == "prose" and (RVT_START.match(line) or VARIANT_START.match(line)):
            if current:
                chunks.append((kind, "\n".join(current), start))
            kind = "rvt" if RVT_START.match(line) else "variant"
            current, start = [], line_no
        current.append(line)
    if current:
        chunks.append((kind, "\n".join(current), start))
    return [c for c in chunks if c[0] != "prose" or c[1].strip()]


class rvt_block(nodes.Element):
    """A parsed rvt directive: its options and edn content"""


class RvtDirective(Directive):
    has_content = True
    optional_arguments = 1
    final_argument_whitespace = True
    option_spec = RVT_OPTIONS

    def run(self):
        block = rvt_block()
        block["title"] = " ".join(self.arguments[0].split()) if self.arguments else None
        block["options"] = {k: "" if v is None else v for k, v in self.options.items()}
        block["content"] = "\n".join(self.content)
        return [block]


directives.register_directive("rvt", RvtDirective)


class rvt_variant(nodes.Element):
    """A parsed rvt-variant directive: its variations and unparsed content"""


class RvtVariantDirective(Directive):
    has_content = True
    option_spec = {"variations": variation_names}

    def run(self):
        if "variations" not in self.options:
            raise self.error("rvt-variant needs a :variations: option")
        node = rvt_variant()
        node["variations"] = self.options["variations"]
        node["content"] = "\n".join(self.content)
        node["offset"] = self.content_offset  # lines before the content
        return [node]


directives.register_directive("rvt-variant", RvtVariantDirective)


class RvtError(ValueError):
    pass


def parse_directive(source, node_class, name):
    """The one `node_class` node of a directive's source, parsed by docutils"""
    stream = _Collect()
    tree = docutils.core.publish_doctree(
        source, settings_overrides={"warning_stream": stream, "report_level": 2,
                                    "halt_level": 5})
    found = list(tree.findall(node_class))
    if stream.messages or len(found) != 1:
        raise RvtError(" ".join(stream.messages) or f"not an {name} directive")
    return found[0]


def parse_rvt(source):
    """(options, content, title) of one rvt directive"""
    block = parse_directive(source, rvt_block, "rvt")
    return block["options"], block["content"], block["title"]


def limit(options, variations):
    """`options` limited to `variations`, or to the ones it names already,
    which must be among them"""
    if "variations" in options:
        outside = [v for v in options["variations"] if v not in variations]
        if outside:
            raise RvtError(f"{', '.join(outside)} is outside its rvt-variant "
                           f"({', '.join(variations)})")
        return options
    return {**options, "variations": variations}


class _Collect:
    def __init__(self):
        self.messages = []

    def write(self, text):
        if text.strip():
            self.messages.append(" ".join(text.split()))


def parse(text, first_line=1):
    """The document's parts. Raises RvtError for a malformed rvt or
    rvt-variant directive and edn errors for unreadable forms."""
    parts = []
    for kind, source, line in split(text):
        line += first_line - 1
        if kind == "prose":
            parts.append(Part(source.strip("\n"), line=line))
        elif kind == "rvt":
            options, content, title = parse_rvt(source)
            for form in edn.read_all(content):
                parts.append(Part(form, options, line, title))
        else:
            variant = parse_directive(source, rvt_variant, "rvt-variant")
            for part in parse(variant["content"], line + variant["offset"]):
                part.options = limit(part.options, variant["variations"])
                parts.append(part)
    return parts


def forms(text):
    return [part.form for part in parse(text)]


def has_rvt(text):
    """True if the document has any rvt block (i.e. it's a script)"""
    return any(ANY_RVT.match(line) for line in text.splitlines())


def definitions_section(parts):
    """Indexes of the parts in rvt blocks marked :definitions:"""
    return [i for i, part in enumerate(parts) if "definitions" in part.options]
