"""Requirements written in reStructuredText

A spec's documents are ordinary rst; each requirement in them is a
``requirement`` directive with its id, and its text is the directive's
content, which may use any rst (lists, emphasis, notes)::

    .. requirement:: VM-EPS-002
       :satisfies: SEG-PWR-004, SEG-PWR-007
       :subsystem: EPS
       :verification: Test

       The VM shall shed loads when the state of charge falls below:

       - 60%: the payload;
       - 40%: everything except the essential loads.

``:satisfies:`` names the requirements this one traces up to; every
other option is an attribute, checked against the spec's schema by the
importer. Everything else in a document (headings, prose, figures) is
documentation; headings give each requirement its section.
"""

import re
from dataclasses import dataclass

import docutils.core
from docutils import nodes
from docutils.parsers.rst import Directive, directives


class requirement_node(nodes.Element):
    """A parsed requirement directive: its id, options and rst text"""


class AnyOption(dict):
    """An option_spec taking every option as plain text"""

    def __missing__(self, name):
        return directives.unchanged

    def __bool__(self):
        return True  # docutils reads no options at all for an empty spec


class RequirementDirective(Directive):
    required_arguments = 1
    has_content = True
    option_spec = AnyOption(satisfies=directives.unchanged)

    def run(self):
        node = requirement_node()
        node["id"] = self.arguments[0].strip()
        node["options"] = {name: " ".join((value or "").split())
                           for name, value in self.options.items()}
        node["text"] = "\n".join(self.content).strip()
        return [node]


class Ignored(Directive):
    """Sphinx directives (toctree, ...) a spec's documents may use, which
    hold no requirements"""
    optional_arguments = 1
    final_argument_whitespace = True
    has_content = True
    option_spec = AnyOption()

    def run(self):
        return []


directives.register_directive("requirement", RequirementDirective)
for name in ("toctree", "only", "index", "tabularcolumns", "highlight"):
    directives.register_directive(name, Ignored)


class RequirementsError(ValueError):
    pass


@dataclass(frozen=True)
class Parsed:
    """A requirement as written: its id, rst text, options (attributes
    and satisfies) and the titles of the sections it is in"""
    id: str
    text: str
    options: dict
    section: tuple = ()

    @property
    def satisfies(self):
        return tuple(sorted({s.strip() for s in self.options.get("satisfies", "").split(",")
                             if s.strip()}))

    @property
    def attributes(self):
        return {k: v for k, v in self.options.items() if k != "satisfies"}


# Messages from roles and directives Sphinx knows and docutils doesn't:
# not errors in a spec
SPHINX_ONLY = re.compile(r'Unknown (interpreted text role|directive type)|'
                         r'No (role|directive) entry for')


class _Collect:
    def __init__(self):
        self.messages = []

    def write(self, text):
        if text.strip() and not SPHINX_ONLY.search(text):
            self.messages.append(" ".join(text.split()))


def doctree(text, source="<string>"):
    stream = _Collect()
    tree = docutils.core.publish_doctree(
        text, source_path=source,
        settings_overrides={"warning_stream": stream, "report_level": 3,
                            "halt_level": 5, "file_insertion_enabled": False,
                            "doctitle_xform": False})
    return tree, stream.messages


def section_of(node):
    titles = []
    parent = node.parent
    while parent is not None:
        if isinstance(parent, nodes.section) and isinstance(parent[0], nodes.title):
            titles.append(parent[0].astext())
        parent = parent.parent
    return tuple(reversed(titles))


def parse(text, source="<string>"):
    """The requirements in an rst document, in order. Raises
    RequirementsError for a malformed directive, empty text or a
    repeated id."""
    tree, messages = doctree(text, source)
    if messages:
        raise RequirementsError("; ".join(messages))
    found, seen = [], set()
    for node in tree.findall(requirement_node):
        id = node["id"]
        if id in seen:
            raise RequirementsError(f"{source}: requirement {id} is defined twice")
        if not node["text"]:
            raise RequirementsError(f"{source}: requirement {id} has no text")
        seen.add(id)
        found.append(Parsed(id, node["text"], node["options"], section_of(node)))
    return found


def plain_text(text):
    """A requirement's rst text as plain words, markup and line breaks
    gone: what its text hash is of"""
    tree, _ = doctree(text)
    return " ".join(tree.astext().split())
