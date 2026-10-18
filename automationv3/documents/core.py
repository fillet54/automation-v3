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
from collections import OrderedDict
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
        document = self.state.document
        serial = getattr(document, "_data_serial", 0)
        document._data_serial = serial + 1
        node = data_block(self.block_text, kind=self.kind, options=options, serial=serial)
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
    """:verdict:`fail`: a state, in bold, classed ``verdict-fail`` so every
    output can style it (\\DUrole{verdict-fail} in LaTeX)"""
    state = utils.unescape(text)
    return [nodes.inline(rawtext, "", nodes.strong(state, state),
                         classes=[f"verdict-{state.replace(' ', '-')}"], verdict=state)], []


roles.register_local_role("verdict", verdict_role)


def anchor_role(name, rawtext, text, lineno, inliner, options=None, content=None):
    """:anchor:`req-BRA-1`: a place pages can link to (#req-bra-1), and
    nothing to read"""
    return [nodes.inline(rawtext, "", ids=[nodes.make_id(utils.unescape(text))])], []


roles.register_local_role("anchor", anchor_role)


# Resolving

def context_of(document):
    """The Context a document is resolved with: set in its settings
    (live), or built from a Sphinx build's configuration"""
    found = getattr(document.settings, "automation", None)
    if found is not None:
        return found
    env = getattr(document.settings, "env", None)
    if env is not None and "automation_root" in env.config:
        from .sphinx import build_context, run_context
        context = build_context(env)
        run = document.get("automation_run")
        return run_context(context, run) if run else context
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
    A resolver that writes nothing removes its placeholder. What they
    write is parsed in one pass (see parse_many), and placeholders that
    writes in turn are resolved the same way.

    With context.extra["blocks"], what each of the document's own
    directives writes is kept in a ``data-block`` container carrying its
    serial (its place among them), so a live page can refresh it alone."""
    first = True
    while True:
        blocks = list(document.findall(data_block))
        inlines = list(document.findall(data_inline))
        if not blocks and not inlines:
            return document
        written = ([RESOLVERS[n["kind"]](context, n["options"]) for n in blocks]
                   + [ROLE_VALUES[n["kind"]](context, n["name"]) for n in inlines])
        parsed = parse_many([str(w) for w in written if w], document)
        for node, rst in zip(blocks + inlines, written):
            found = parsed[str(rst)]() if rst else []
            if isinstance(node, data_inline):
                found = inline_of(found)
            elif first and context.extra.get("blocks"):
                found = [nodes.container("", *found, classes=["data-block"],
                                         serial=node["serial"], kind=node["kind"])]
            node.replace_self(found)
        first = False


class fragment_end(nodes.Element):
    """Where one fragment of a batch ends (see parse_many)"""


class FragmentEnd(Directive):
    def run(self):
        return [fragment_end()]


directives.register_directive("data-fragment-end", FragmentEnd)
FRAGMENT_END = "\n\n.. data-fragment-end::\n\n"

# rst -> its parsed nodes, unresolved: what snippets write repeats (every
# pending step's result, a finished step's on every poll)
_fragments = OrderedDict()
FRAGMENT_CACHE = 20000


def parse_many(texts, document):
    """rst -> a function giving fresh nodes it parses to, as body content
    of `document`, for each of `texts`. Those not parsed before are
    parsed together, in one pass."""
    wanted = list(dict.fromkeys(texts))
    missing = [t for t in wanted if t not in _fragments]
    if missing:
        batch = utils.new_document(document.get("source", "<data>"), document.settings)
        batch._data_transform = True  # resolved by the caller, not as a transform
        Parser().parse(FRAGMENT_END.join(missing) + FRAGMENT_END, batch)
        for message in list(batch.findall(nodes.system_message)):
            if message["level"] < 2:
                message.parent.remove(message)
        chunk, chunks = [], []
        for child in list(batch.children):
            if isinstance(child, fragment_end):
                chunks.append(chunk)
                chunk = []
            else:
                chunk.append(child)
        for text, found in zip(missing, chunks):
            _fragments[text] = found
        while len(_fragments) > FRAGMENT_CACHE:
            _fragments.popitem(last=False)
    for text in wanted:
        _fragments.move_to_end(text)
    return {t: (lambda found=_fragments[t]: [n.deepcopy() for n in found]) for t in wanted}


def parse_fragment(rst, document):
    """The nodes `rst` parses to, as body content of `document`, resolved"""
    holder = nodes.container()
    holder.extend(parse_many([str(rst)], document)[str(rst)]())
    holder.document = document
    wrapper = utils.new_document(document.get("source", "<data>"), document.settings)
    wrapper += holder
    resolve(wrapper, context_of(document) or Context())
    return list(holder.children)


def inline_of(found):
    if len(found) == 1 and isinstance(found[0], nodes.paragraph):
        return list(found[0].children)
    return [nodes.inline("", "", *found)]


# Rendering

SETTINGS = {
    "report_level": 3, "halt_level": 5, "doctitle_xform": False,
    "file_insertion_enabled": False, "raw_enabled": False,
    "initial_header_level": 2, "syntax_highlight": "short",
}


LATEX_DEFAULTS = {"legacy_column_widths": False, "use_latex_citations": True}


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


def resolved_block(doctree, serial, context):
    """A document holding only the directive numbered `serial` in a
    parsed doctree, resolved; None if there is no such directive"""
    node = next((n for n in doctree.findall(data_block) if n["serial"] == serial), None)
    if node is None:
        return None
    document = utils.new_document("<block>", copy.copy(doctree.settings))
    document.settings.automation = context
    document += node.deepcopy()
    return resolve(document, context)


def write(document, writer="html5", settings=None):
    """docutils' parts for a resolved doctree; `writer` is a writer's
    name or a Writer"""
    output = io.StringIO()
    publisher = docutils.core.Publisher(
        reader=doctree_reader.Reader(parser_name="null"),
        source=docutils_io.DocTreeInput(document),
        destination_class=docutils_io.StringOutput)
    if isinstance(writer, str):
        publisher.set_writer(writer)
    else:
        publisher.writer = writer
    defaults = LATEX_DEFAULTS if writer == "latex" else {}
    publisher.process_programmatic_settings(None, {**SETTINGS, **defaults, **(settings or {}),
                                                   "warning_stream": output}, None)
    publisher.set_destination(None, None)
    publisher.publish()
    return publisher.writer.parts
