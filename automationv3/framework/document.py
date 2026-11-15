"""What is left of the old script reader, for cards.py until it reads
the tree (step 3 of plans/source-tree.md), and the line tests used to
tell scripts apart. Scripts are read by source.py.
"""

import re

from . import source as source_tree
from .source import rvt_block, rvt_variant  # noqa: F401  (cards.py)

RVT_START = re.compile(r"^\.\. rvt::(\s.*)?$")
VARIANT_START = re.compile(r"^\.\. rvt-variant::\s*$")
ANY_RVT = re.compile(r"^\s*\.\. rvt::(\s.*)?$")


def has_rvt(text):
    """True if the document has any rvt block (i.e. it's a script)"""
    return any(ANY_RVT.match(line) for line in text.splitlines())


class RvtError(ValueError):
    pass


def parse_directive(source, node_class, name):
    """The one `node_class` node of a directive's source, read by
    source.parse: a copy, with the attributes this module reads
    ("content", "offset": the lines before the content)"""
    tree = source_tree.parse(source)
    found = [n for n in tree.children if isinstance(n, node_class)]
    messages = [" ".join(text.split()) for level, _, text in tree.messages if level >= 2]
    problems = [p.message for n in found for p in n["problems"]]
    if messages or problems or len(found) != 1:
        raise RvtError(" ".join(messages + problems) or f"not an {name} directive")
    node = found[0].copy()
    node["offset"] = node["content_offset"]
    if node_class is rvt_block:
        node["content"] = node["code"]
    return node


def content_position(source, content, offset):
    """For a directive's `content` (as docutils gives it: dedented) that
    starts `offset` lines into its `source`: functions mapping a 0-based
    content line to its 0-based line in `source`, and to how far its
    columns moved when the content was dedented"""
    source_lines = source.splitlines()
    content_lines = content.splitlines()

    def indent(line):
        return len(line) - len(line.lstrip())

    def col_shift(i):
        if i < len(content_lines) and offset + i < len(source_lines):
            original, dedented = source_lines[offset + i], content_lines[i]
            if dedented.strip():
                return indent(original) - indent(dedented)
        return shifts[0] if shifts else 0

    shifts = [indent(source_lines[offset + i]) - indent(line)
              for i, line in enumerate(content_lines)
              if line.strip() and offset + i < len(source_lines)]
    return (lambda i: offset + i), col_shift


HEADING_LINE = re.compile(r"^([=\-~`#\"^+*:.'_])\1+\s*$")


def document_title(text):
    """The document's first section title (a line underlined, and maybe
    overlined, with punctuation as long as it), or None"""
    lines = text.splitlines()
    for i in range(len(lines) - 1):
        title, under = lines[i].strip(), lines[i + 1].rstrip()
        if (title and not HEADING_LINE.match(lines[i]) and HEADING_LINE.match(under)
                and len(under) >= len(title)):
            return title
    return None
