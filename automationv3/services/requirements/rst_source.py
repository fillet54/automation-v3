"""Requirements written in reStructuredText

A requirements document is an ordinary rst document; each requirement in
it is a ``requirement`` directive with its id, and its text is the
directive's content, which may use any rst (lists, emphasis, notes)::

    .. requirement:: VM-EPS-002
       :subsystem: EPS

       The VM shall shed loads when the state of charge falls below:

       - 60%: the payload;
       - 40%: everything except the essential loads.

The subsystem is the ``:subsystem:`` option if given, else the middle
part of a three-part id (``VM-EPS-002`` is ``EPS``), else the part before
the first dash. Everything else in the document (headings, prose) is
documentation and is ignored.
"""

import docutils.core
from docutils import nodes
from docutils.parsers.rst import Directive, directives

from ...framework.requirement import Requirement


class requirement_node(nodes.Element):
    """A parsed requirement directive: its id, options and rst text"""


class RequirementDirective(Directive):
    required_arguments = 1
    has_content = True
    option_spec = {"subsystem": directives.unchanged}

    def run(self):
        node = requirement_node()
        node["id"] = self.arguments[0].strip()
        node["subsystem"] = self.options.get("subsystem")
        node["text"] = "\n".join(self.content).strip()
        return [node]


directives.register_directive("requirement", RequirementDirective)


def subsystem_of(id):
    parts = id.split("-")
    if len(parts) >= 3:
        return parts[1]
    return parts[0]


class RequirementsError(ValueError):
    pass


class _Collect:
    def __init__(self):
        self.messages = []

    def write(self, text):
        if text.strip():
            self.messages.append(" ".join(text.split()))


def parse(text):
    """The Requirements of an rst requirements document. Raises
    RequirementsError for a malformed directive or a repeated id."""
    stream = _Collect()
    tree = docutils.core.publish_doctree(
        text, settings_overrides={"warning_stream": stream, "report_level": 3,
                                  "halt_level": 5})
    if stream.messages:
        raise RequirementsError("; ".join(stream.messages))
    found, seen = [], set()
    for node in tree.findall(requirement_node):
        id = node["id"]
        if id in seen:
            raise RequirementsError(f"requirement {id} is defined twice")
        if not node["text"]:
            raise RequirementsError(f"requirement {id} has no text")
        seen.add(id)
        found.append(Requirement(id=id, text=node["text"],
                                 subsystem=node["subsystem"] or subsystem_of(id)))
    return found
