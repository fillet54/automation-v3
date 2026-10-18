"""Directives and roles whose content comes from data

A data directive (``.. results::``) or role (``:report:`number```) parses
to a placeholder that holds only its name and options: parsing never
reads data, so a parsed document can be cached and reused. Resolving
replaces each placeholder with what its resolver writes, which is always
reStructuredText (usually a snippet, see template.py), parsed in place.

The same directives work in two hosts:

- live pages parse once with plain docutils (cached), then resolve a
  copy of the tree against the data as it is now, and write HTML;
- Sphinx builds resolve while reading (ResolveTransform), so what they
  write goes through Sphinx like any other content.

A resolver is ``fn(context, options) -> rst``; `context` is a Context:
the data (a ReportData, or None for a page with no data yet), the run a
run document is about, the snippets, and which host is rendering.
Directives and roles are added with `directive` and `role`; plugins add
their own the same way (see framework/plugins.py).
"""

import copy
import io
from dataclasses import dataclass, field

import docutils.core
from docutils import io as docutils_io
from docutils import nodes, utils
from docutils.parsers.rst import Directive, Parser, directives, roles
from docutils.readers import doctree as doctree_reader
from docutils.transforms import Transform

from .template import Snippets

LIVE, EXPORT = "live", "export"


@dataclass
class Context:
    data: object = None          # a ReportData, or None
    run: dict = None             # the run a run document is about
    snippets: Snippets = field(default_factory=Snippets)
    host: str = LIVE
    exported: str = ""           # when an export was made
    manifest_hash: str = ""
    extra: dict = field(default_factory=dict)

    def render(self, name, **values):
        return self.snippets.render(name, data=self.data, run=self.run, context=self,
                                    **values)


# The placeholders

class data_block(nodes.General, nodes.Element):
    """A data directive, until resolved: ["kind"] and ["options"]"""


class data_inline(nodes.Inline, nodes.TextElement):
    """A data role, until resolved: ["kind"] and ["name"]"""


RESOLVERS = {}       # directive name -> fn(context, options) -> rst
ROLE_VALUES = {}     # role name -> fn(context, name) -> rst (inline)


class DataDirective(Directive):
    has_content = False
    optional_arguments = 1
    final_argument_whitespace = True
    option_spec = {}
    kind = None

    def run(self):
        options = dict(self.options)
        if self.arguments:
            options["argument"] = self.arguments[0]
        node = data_block(self.block_text, kind=self.kind, options=options)
        node.line = self.lineno
        note_transform(self.state.document)
        return [node]


def directive(name, resolver, option_spec=None, arguments=False):
    """Add a data directive `name`, written by `resolver(context, options)`.
    With `arguments`, its one argument is options["argument"]."""
    cls = type(f"Data_{name}", (DataDirective,), {
        "kind": name, "option_spec": dict(option_spec or {}),
        "optional_arguments": 1 if arguments else 0})
    RESOLVERS[name] = resolver
    directives.register_directive(name, cls)
    return cls


def role(name, value):
    """Add a data role `name`: :name:`what` is written by value(context,
    what), as inline rst"""
    def run(role_name, rawtext, text, lineno, inliner, options=None, content=None):
        note_transform(inliner.document)
        return [data_inline(rawtext, kind=name, name=utils.unescape(text))], []
    ROLE_VALUES[name] = value
    roles.register_local_role(name, run)


def verdict_role(name, rawtext, text, lineno, inliner, options=None, content=None):
    """:verdict:`fail`: a state, classed so every output can style it"""
    state = utils.unescape(text)
    return [nodes.strong(rawtext, state, classes=["verdict", state.replace(" ", "-")])], []


roles.register_local_role("verdict", verdict_role)


# Resolving

def context_of(document):
    """The Context a document is resolved with: set in its settings
    (live), or built from a Sphinx build's configuration"""
    found = getattr(document.settings, "automation", None)
    if found is not None:
        return found
    env = getattr(document.settings, "env", None)
    if env is not None:
        from .sphinx import build_context
        return build_context(env)
    return None


class ResolveTransform(Transform):
    """Resolves a document's placeholders while it is read, when its
    settings carry a Context (Sphinx builds, one-off renders)"""

    default_priority = 200

    def apply(self):
        context = context_of(self.document)
        if context is not None:
            resolve(self.document, context)


def note_transform(document):
    if not getattr(document, "_data_transform", False):
        document._data_transform = True
        document.transformer.add_transform(ResolveTransform)


def resolve(document, context):
    """Replace every placeholder in `document` with what it resolves to.
    A resolver that writes nothing removes its placeholder."""
    for node in list(document.findall(data_block)):
        rst = RESOLVERS[node["kind"]](context, node["options"])
        node.replace_self(parse_fragment(rst, document) if rst else [])
    for node in list(document.findall(data_inline)):
        rst = ROLE_VALUES[node["kind"]](context, node["name"])
        node.replace_self(parse_inline(rst, document) if rst else [])
    return document


def parse_fragment(rst, document):
    """The nodes `rst` parses to, as body content of `document`"""
    fragment = utils.new_document(document.get("source", "<data>"), document.settings)
    fragment._data_transform = True  # resolved here and now, not again
    Parser().parse(str(rst), fragment)
    for message in list(fragment.findall(nodes.system_message)):
        if message["level"] < 2:
            message.parent.remove(message)
    resolve(fragment, context_of(document) or Context())
    return list(fragment.children)


def parse_inline(rst, document):
    found = parse_fragment(rst, document)
    if len(found) == 1 and isinstance(found[0], nodes.paragraph):
        return list(found[0].children)
    return [nodes.inline("", "", *found)]


# Rendering

SETTINGS = {
    "report_level": 3, "halt_level": 5, "doctitle_xform": False,
    "file_insertion_enabled": False, "raw_enabled": False,
    "initial_header_level": 2, "syntax_highlight": "short",
}


def parse(source, settings=None, source_path="<document>"):
    """The doctree of `source`, placeholders left in place"""
    overrides = {**SETTINGS, **(settings or {}), "automation": None}
    return docutils.core.publish_doctree(source, source_path=source_path,
                                         settings_overrides=overrides)


def resolved(doctree, context):
    """A resolved copy of a parsed (perhaps cached) doctree"""
    document = doctree.deepcopy()
    document.settings = copy.copy(doctree.settings)
    document.settings.automation = context
    return resolve(document, context)


def write(document, writer_name="html5", settings=None):
    """docutils' parts for a resolved doctree"""
    output = io.StringIO()
    publisher = docutils.core.Publisher(
        reader=doctree_reader.Reader(parser_name="null"),
        source=docutils_io.DocTreeInput(document),
        destination_class=docutils_io.StringOutput)
    publisher.set_writer(writer_name)
    publisher.process_programmatic_settings(None, {**SETTINGS, **(settings or {}),
                                                   "warning_stream": output}, None)
    publisher.set_destination(None, None)
    publisher.publish()
    return publisher.writer.parts
