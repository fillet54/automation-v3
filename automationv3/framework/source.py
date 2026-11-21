"""A script's source as one docutils tree

A script (and a core.rst) is an ordinary reStructuredText document. Its
code lives in `rvt` directives whose content is edn forms::

    Steps
    -----

    .. rvt::
       :definitions:

       (def approach-deg 16)

    .. rvt:: On the load's approach angle
       :variations: standard, extended

       (Verify (approach-angle) within? (- approach-deg 2.5) (+ approach-deg 2.5))

    .. rvt-variant::
       :variations: extended

       The extended approach comes in steeper.

       .. rvt::

          (Verify truth.downrange > -6000)

`parse` reads the whole file with docutils once. The two directives
become nodes in that tree:

- `rvt_block`: one rvt directive, its title, options, lines, code and
  the forms read from it, each form's spans already in file
  coordinates (1-based lines, 0-based columns);
- `rvt_variant`: an rvt-variant directive, whose content is parsed in
  place, so its prose and blocks are its children;
- `requirement_reference`: a :req:`ID` role, holding only the id;
  looking the requirement up happens when a page is rendered (see
  rst.RequirementReferences).

Neither directive ever fails: they take any option and argument, and
what is wrong with them (an unknown option, a flag given a value, a
variant with no variations, code that doesn't read) is a problem on
the node, with a span. So a bad block still has its exact lines.

docutils knows where a directive is to the line; where a title or a
:req: role is, `locate` finds, from the lines around them.
"""

import functools
import re
from dataclasses import dataclass
from typing import NamedTuple

from docutils import frontend, nodes, utils
from docutils.parsers.rst import Directive, Parser, directives, roles

from . import edn


class Problem(NamedTuple):
    """Something wrong in the source, and where (an edn.Span)"""

    message: str
    span: edn.Span


# The nodes


class rvt_block(nodes.Element):
    """An rvt directive.

    title        its title, whitespace collapsed, or None
    options      the options that are right, read: {"definitions": "",
                 "table": "", "variations": [names]}
    variations   its own :variations:, else its variant's, else None
    line, end    its first and last line in the file
    content_offset
                 docutils' own: the 0-based line its content starts on
    content_line the file line of its code's first line, or None
    indent       how far its code is indented in the file
    code         its content, dedented, as text
    forms        [(form, span)] read from the code, spans in the file;
                 if it stops reading, the forms before that
    error        a Problem if the code stops reading, else None
    problems     [Problem]: what is wrong with its title and options"""

    @property
    def key(self):
        return (self["line"], self["end"])

    @property
    def title(self):
        return self["title"]

    @property
    def options(self):
        return self["options"]

    @property
    def variations(self):
        return self["variations"]

    @property
    def own_variations(self):
        return self["options"].get("variations")

    @property
    def is_definitions(self):
        return "definitions" in self["options"]

    @property
    def is_table(self):
        return "table" in self["options"]

    @property
    def line_start(self):
        return self["line"]

    @property
    def line_end(self):
        return self["end"]

    @property
    def content_offset(self):
        return self["content_offset"]

    @property
    def content_line(self):
        return self["content_line"]

    @property
    def indent(self):
        return self["indent"]

    @property
    def code(self):
        return self["code"]

    @property
    def forms(self):
        return self["forms"]

    @property
    def error(self):
        return self["error"]

    @property
    def problems(self):
        return self["problems"]


class rvt_variant(nodes.Element):
    """An rvt-variant directive; its content parsed in place, as its
    children.

    variations   its :variations: (within its own variant's), or []
    line, end    its first and last line in the file
    content_offset, content_line, indent
                 as for rvt_block
    content      its content, dedented, as text
    problems     [Problem]"""

    @property
    def key(self):
        return (self["line"], self["end"])

    @property
    def variations(self):
        return self["variations"]

    @property
    def line_start(self):
        return self["line"]

    @property
    def line_end(self):
        return self["end"]

    @property
    def content_offset(self):
        return self["content_offset"]

    @property
    def content_line(self):
        return self["content_line"]

    @property
    def indent(self):
        return self["indent"]

    @property
    def content(self):
        return self["content"]

    @property
    def problems(self):
        return self["problems"]


class requirement_reference(nodes.Inline, nodes.TextElement):
    """A :req:`ID` role: ["id"], and ["lineno"], the first line of the
    paragraph it is in"""


# Options


def variation_names(argument):
    """The names of a `:variations:` option, as a list"""
    names = [name.strip() for name in (argument or "").split(",")]
    if not all(names):
        raise ValueError("expected variation names separated by commas")
    return names


class AnyOption(dict):
    """An option spec that takes any option name, its value as plain
    text: the directive checks them, so docutils never rejects one"""

    def __bool__(self):  # docutils reads an empty spec as "no options"
        return True

    def __contains__(self, name):
        return True

    def __getitem__(self, name):
        return directives.unchanged

    def get(self, name, default=None):
        return directives.unchanged


FLAGS = ("definitions", "table")


def _indent(line):
    return len(line) - len(line.lstrip())


class _Source(Directive):
    """What the two directives share: where they are, and their problems"""

    has_content = True
    optional_arguments = 1
    final_argument_whitespace = True
    option_spec = AnyOption()

    def place(self, node):
        """Set the node's lines, and how far its content is indented in
        the file. A directive inside an rvt-variant is read from the
        variant's dedented content, so the variant's indent is added."""
        lines = self.block_text.splitlines()
        node["line"] = self.lineno
        node["end"] = self.lineno + max(len(lines), 1) - 1
        node["content_offset"] = self.content_offset
        node["problems"] = []
        self.within = self.variant()
        self.outer = self.within["variations"] if self.within is not None else None
        base = self.variant_indent()
        self.shifts = {}  # content line -> how far it was dedented, non-blank ones
        for i, line in enumerate(self.content):
            at = self.content.offset(i) - (self.lineno - 1)  # its line in block_text
            if line.strip() and 0 <= at < len(lines):
                self.shifts[i] = base + _indent(lines[at]) - _indent(line)
        node["indent"] = next(iter(self.shifts.values()), base)  # blank lines: the first's
        node["content_line"] = self.content.offset(0) + 1 if self.content else None

    def variant(self):
        """The rvt-variant this directive is inside, or None"""
        parent = self.state.parent
        while parent is not None and not isinstance(parent, rvt_variant):
            parent = parent.parent
        return parent

    def line_span(self, node, line):
        """The span of a whole line of this directive (1-based)"""
        lines = self.block_text.splitlines()
        text = lines[line - node["line"]] if 0 <= line - node["line"] < len(lines) else ""
        col = _indent(text) + self.variant_indent()
        return edn.Span(line, col, line, col + len(text.strip()), self.path())

    def variant_indent(self):
        return self.within["indent"] if self.within is not None else 0

    def option_line(self, node, name):
        """The line its :name: option is on"""
        for n, line in enumerate(self.block_text.splitlines()):
            if line.strip().startswith(f":{name}:"):
                return node["line"] + n
        return node["line"]

    def problem(self, node, message, line=None):
        node["problems"].append(Problem(message, self.line_span(node, line or node["line"])))

    def path(self):
        return getattr(self.state.document, "script_path", None)

    def read_variations(self, node):
        """Its :variations:, checked against those of the variant it is in"""
        outer = self.outer
        if "variations" not in self.options:
            return None
        try:
            names = variation_names(self.options["variations"])
        except ValueError as error:
            self.problem(node, f":variations: {error}", self.option_line(node, "variations"))
            return None
        if outer:
            outside = [name for name in names if name not in outer]
            if outside:
                self.problem(node, f"{', '.join(outside)} is outside its rvt-variant "
                                   f"({', '.join(outer)})", self.option_line(node, "variations"))
        return names

    def file_position(self, node):
        """Functions mapping a 0-based content line to its file line
        (1-based), and to how far its columns moved"""
        first = node["content_line"] or 1
        shifts, indent = self.shifts, node["indent"]
        return (lambda i: first + i), (lambda i: shifts.get(i, indent))


class RvtDirective(_Source):

    def run(self):
        node = rvt_block(self.block_text)
        self.place(node)
        node["title"] = " ".join(self.arguments[0].split()) if self.arguments else None
        options = {}
        for name, value in self.options.items():
            if name in FLAGS:
                if value:
                    self.problem(node, f":{name}: takes no value", self.option_line(node, name))
                else:
                    options[name] = ""
            elif name != "variations":
                self.problem(node, f'unknown option: "{name}"', self.option_line(node, name))
        own = self.read_variations(node)
        if own is not None:
            options["variations"] = own
        node["options"] = options
        node["variations"] = own if own is not None else (self.outer or None)
        node["code"] = "\n".join(self.content)
        self.read_code(node)
        return [node]

    def read_code(self, node):
        line_of, col_shift = self.file_position(node)
        path = self.path()
        node["error"] = None
        try:
            found = edn.read_all_with_spans(node["code"])
        except Exception as error:  # noqa: BLE001  what failed is the problem
            found = edn.read_all_with_spans(node["code"], readable=True)
            line = getattr(error, "line", 0)
            col = getattr(error, "col", 0)
            at = line_of(line)
            message = str(error).rsplit(" (line:", 1)[0]  # the span says where
            node["error"] = Problem(
                message, edn.Span(at, col + col_shift(line), at, col + col_shift(line) + 1,
                                     path))
        forms = []
        for form, span in found:
            edn.move_spans(form, line_of, col_shift, path)
            if span is not None:
                span = span.moved(line_of, col_shift, path)
            forms.append((form, span))
        node["forms"] = forms


class RvtVariantDirective(_Source):

    def run(self):
        node = rvt_variant(self.block_text)
        self.place(node)
        for name in self.options:
            if name != "variations":
                self.problem(node, f'unknown option: "{name}"', self.option_line(node, name))
        if self.arguments:
            self.problem(node, "rvt-variant takes no title")
        names = self.read_variations(node)
        if names is None and "variations" not in self.options:
            self.problem(node, "rvt-variant needs a :variations: option")
        node["variations"] = names or []
        node["content"] = "\n".join(self.content)
        self.state.nested_parse(self.content, self.content_offset, node, match_titles=True)
        return [node]


def requirement_role(role, rawtext, text, lineno, inliner, options=None, content=None):
    """:req:`ID`: records the id; see rst.RequirementReferences"""
    id = utils.unescape(text).strip()
    return [requirement_reference(rawtext, id, id=id, lineno=lineno)], []


directives.register_directive("rvt", RvtDirective)
directives.register_directive("rvt-variant", RvtVariantDirective)
roles.register_canonical_role("REQ", requirement_role)


# Parsing

SETTINGS = {"report_level": 5, "halt_level": 5, "doctitle_xform": False,
            "file_insertion_enabled": False, "raw_enabled": False}

# docutils messages that only mean Sphinx (or a plugin) knows the
# directive or role: not problems in the script
NOT_PROBLEMS = ("Unknown interpreted text role", "Unknown directive type",
                "No role entry for", "No directive entry for")


@functools.cache
def _settings():
    return frontend.get_default_settings(Parser)


@functools.lru_cache(maxsize=256)
def parse(text, path=None):
    """The docutils tree of a script's `text`, read from `path` (which
    its spans name). Cached: the tree is shared, so anything that
    changes it must copy it first (document.deepcopy()). Never raises:
    what is wrong is in `problems`.

    The tree is the parser's alone: no transforms run, so sections and
    titles stay where the file has them. Besides its nodes it carries
    `lines` (the file's lines) and `messages` (every docutils message,
    as (level, line or None, text))."""
    settings = _settings().copy()
    for name, value in SETTINGS.items():
        setattr(settings, name, value)
    tree = utils.new_document(path or "<script>", settings)
    tree.script_path = path
    tree.lines = text.splitlines()
    tree.messages = []

    def note(message):
        tree.messages.append((message["level"], message.get("line"),
                              message.children[0].astext() if message.children else ""))

    tree.reporter.attach_observer(note)
    try:
        Parser().parse(text, tree)
    except Exception as error:  # noqa: BLE001  never raise: report it
        tree.messages.append((4, None, f"could not be parsed: {error}"))
    return tree


# What the tree holds


def blocks(node):
    """The rvt_block and rvt_variant nodes directly in `node` (a tree, a
    section or a variant), in file order: those inside a variant are
    blocks(variant)"""
    found = []
    for child in node.children:
        if isinstance(child, (rvt_block, rvt_variant)):
            found.append(child)
        elif isinstance(child, nodes.Element):
            found += blocks(child)
    return found


def walk(node):
    """Every rvt_block and rvt_variant at any depth, in file order"""
    for found in blocks(node):
        yield found
        if isinstance(found, rvt_variant):
            yield from walk(found)


@dataclass
class Statement:
    """One form of an rvt block, as running and checking see it: its
    place among the script's forms (`index`), and its block's fields"""

    form: object
    span: edn.Span
    block: rvt_block
    index: int
    table_rows: bool = False  # the first form of a :table: block: its rows

    @property
    def options(self):
        return self.block["options"]

    @property
    def variations(self):
        """The variation names its block is limited to, else None (all)"""
        return self.block["variations"]

    @property
    def title(self):
        return self.block["title"]

    @property
    def line(self):
        """Where its block starts"""
        return self.block["line"]

    @property
    def table(self):
        """Its block's line, if the block is a :table:, else None"""
        return self.block["line"] if "table" in self.options else None

    @property
    def definitions(self):
        """Whether its block is the definitions section"""
        return "definitions" in self.options

    def applies(self, variation):
        """True if it runs for `variation` (None: no variation)"""
        return variation is None or self.variations is None or variation in self.variations


def statements(tree):
    """Each form of each rvt block, in file order (see Statement).
    Shared: kept on the tree, which parse caches."""
    found = getattr(tree, "_statements", None)
    if found is None:
        found = []
        for block in walk(tree):
            if isinstance(block, rvt_block):
                table = "table" in block["options"]
                for n, (form, span) in enumerate(block["forms"]):
                    found.append(Statement(form, span, block, len(found), table and n == 0))
        tree._statements = found
    return found


def table_steps(found, index):
    """The indexes of the steps of the table block whose rows are
    statement `index` of `found`"""
    rows = found[index]
    return [s.index for s in found[index + 1:] if s.block is rows.block]


def unreadable(tree):
    """The Problems that stop the source being read as a script: those
    of its blocks and variants, code that doesn't read, and directives
    docutils read as a paragraph's text (not its own messages about
    prose)"""
    found = []
    for node in walk(tree):
        found += node["problems"]
        if node.get("error"):
            found.append(node["error"])
    return found + swallowed(tree)


ANY_RVT = re.compile(r"^\s*\.\. rvt::(\s.*)?$")


def has_rvt(text):
    """True if the document has any rvt block (i.e. it's a script): a
    cheap line test, without parsing (when listing a folder, say)"""
    return any(ANY_RVT.match(line) for line in text.splitlines())


DIRECTIVE_LINE = re.compile(r"^\s*\.\. (rvt|rvt-variant)::")


def swallowed(tree):
    """Problems for each `.. rvt::` (or `.. rvt-variant::`) line that is
    part of a paragraph, because no blank line comes before it: docutils
    reads it as text, so it would never run"""
    paragraphs = {line.strip() for node in tree.findall(nodes.paragraph)
                  for line in node.rawsource.splitlines()[1:]}
    found = []
    for i, line in enumerate(tree.lines):
        if DIRECTIVE_LINE.match(line) and i and tree.lines[i - 1].strip() \
                and line.strip() in paragraphs:
            col = _indent(line)
            found.append(Problem(f"{line.strip()} needs a blank line before it: without one "
                                 "it is read as part of the paragraph above",
                                 edn.Span(i + 1, col, i + 1, len(line.rstrip()),
                                          tree.script_path)))
    return found


def title(tree):
    """The text of the document's first title, or None"""
    found = next(tree.findall(nodes.title), None)
    return found.astext() if found is not None else None


def problems(tree):
    """Every Problem in the source, in file order: those on blocks and
    variants, code that doesn't read, and docutils' messages at error
    level and above"""
    found = unreadable(tree)
    path = getattr(tree, "script_path", None)
    for level, line, text in tree.messages:
        if level >= 3 and not text.startswith(NOT_PROBLEMS):
            at = line or 1
            length = len(tree.lines[at - 1]) if 0 < at <= len(tree.lines) else 0
            found.append(Problem(" ".join(text.split()), edn.Span(at, 0, at, length, path)))
    return sorted(found, key=lambda p: (p.span.line, p.span.col))


# Where things are


def locate(tree, node):
    """Where a title or a requirement_reference is in the file, as an
    edn.Span, or None if it can't be found. docutils gives a title the
    line of its underline at the top level and none inside a variant,
    and a role only its paragraph's first line; so this finds the
    node's own text in the lines around it."""
    return _positions(tree).get(id(node))


def _positions(tree):
    found = getattr(tree, "_positions", None)
    if found is None:
        found = tree._positions = {}
        _locate_titles(tree, found)
        _locate_references(tree, found)
    return found


def _is_adornment(line):
    """A line of one punctuation character repeated (indented, inside a
    variant)"""
    stripped = line.strip()
    return len(stripped) >= 2 and not stripped[0].isalnum() \
        and stripped == stripped[0] * len(stripped)


def _locate_titles(tree, found):
    """Titles in file order: each is the next line, from where the last
    one was found, with its text and an adornment under it"""
    lines, path, cursor = tree.lines, tree.script_path, 0
    for node in tree.findall(nodes.title):
        text = node.rawsource.strip() or node.astext().strip()
        hint = node.line - 2 if node.line else None  # the underline's line, 1-based
        candidates = ([hint] if hint is not None and hint >= cursor else []) + list(
            range(cursor, len(lines) - 1))
        for i in candidates:
            if lines[i].strip() == text and _is_adornment(lines[i + 1]):
                col = _indent(lines[i])
                found[id(node)] = edn.Span(i + 1, col, i + 1, col + len(text), path)
                cursor = i + 2
                break


def _locate_references(tree, found):
    """A role is in the paragraph that starts at its line: find its raw
    text there, after any found before it in the same paragraph"""
    lines, path = tree.lines, tree.script_path
    after = {}  # paragraph line -> (line, col) searched from
    for node in tree.findall(requirement_reference):
        start = node["lineno"]
        line, col = after.get(start, (start, 0))
        raw = node.rawsource
        for i in range(line - 1, len(lines)):
            at = lines[i].find(raw, col if i == line - 1 else 0)
            if at >= 0:
                found[id(node)] = edn.Span(i + 1, at, i + 1, at + len(raw), path)
                after[start] = (i + 1, at + len(raw))
                break
            if i > line - 1 and not lines[i].strip():
                break  # the paragraph ended


def requirement_refs(tree):
    """[(id, span)] for every :req: reference, in file order"""
    return [(node["id"], locate(tree, node)) for node in tree.findall(requirement_reference)]
