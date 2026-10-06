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

The document is split at its rvt directives. The prose between them
stays rst; each rvt directive is parsed by docutils (so its options are
read properly) and its content read as edn. A document's parts are the
prose chunks and the forms, in order: each prose chunk is a plain
string, each form carries its block's options.
"""

import re
from dataclasses import dataclass, field

import docutils.core
import docutils.utils
from docutils import nodes
from docutils.parsers.rst import Directive, directives

from . import edn

RVT_START = re.compile(r"^\.\. rvt::\s*$")


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

    @property
    def variations(self):
        """The variation names this part is limited to, else None (all)"""
        return self.options.get("variations")

    def applies(self, variation):
        """True if the part runs for `variation` (None: no variation)"""
        return variation is None or self.variations is None or variation in self.variations

    @property
    def prose(self):
        return isinstance(self.form, str) and not isinstance(
            self.form, (edn.Symbol, edn.Keyword))


def split(text):
    """Chunks of (is_rvt, source, line): prose and rvt directives, in order.

    An rvt directive runs from its `.. rvt::` line through every
    indented or blank line after it.
    """
    chunks, current, line_no, start = [], [], 0, 1
    in_rvt = False
    for line_no, line in enumerate(text.splitlines(), start=1):
        if in_rvt and line.strip() and not line[0].isspace():
            chunks.append((True, "\n".join(current), start))
            current, start, in_rvt = [], line_no, False
        if not in_rvt and RVT_START.match(line):
            if current:
                chunks.append((False, "\n".join(current), start))
            current, start, in_rvt = [], line_no, True
        current.append(line)
    if current:
        chunks.append((in_rvt, "\n".join(current), start))
    return [c for c in chunks if c[0] or c[1].strip()]


class rvt_block(nodes.Element):
    """A parsed rvt directive: its options and edn content"""


class RvtDirective(Directive):
    has_content = True
    option_spec = RVT_OPTIONS

    def run(self):
        block = rvt_block()
        block["options"] = {k: "" if v is None else v for k, v in self.options.items()}
        block["content"] = "\n".join(self.content)
        return [block]


directives.register_directive("rvt", RvtDirective)


class RvtError(ValueError):
    pass


def parse_rvt(source):
    """(options, content) of one rvt directive, parsed by docutils"""
    stream = _Collect()
    tree = docutils.core.publish_doctree(
        source, settings_overrides={"warning_stream": stream, "report_level": 2,
                                    "halt_level": 5})
    blocks = list(tree.findall(rvt_block))
    if stream.messages or len(blocks) != 1:
        raise RvtError(" ".join(stream.messages) or "not an rvt directive")
    return blocks[0]["options"], blocks[0]["content"]


class _Collect:
    def __init__(self):
        self.messages = []

    def write(self, text):
        if text.strip():
            self.messages.append(" ".join(text.split()))


def parse(text):
    """The document's parts. Raises RvtError for a malformed rvt block
    and edn errors for unreadable forms."""
    parts = []
    for is_rvt, source, line in split(text):
        if not is_rvt:
            parts.append(Part(source.strip("\n"), line=line))
            continue
        options, content = parse_rvt(source)
        for form in edn.read_all(content):
            parts.append(Part(form, options, line))
    return parts


def forms(text):
    return [part.form for part in parse(text)]


def has_rvt(text):
    """True if the document has any rvt block (i.e. it's a script)"""
    return any(RVT_START.match(line) for line in text.splitlines())


def definitions_section(parts):
    """Indexes of the parts in rvt blocks marked :definitions:"""
    return [i for i, part in enumerate(parts) if "definitions" in part.options]
