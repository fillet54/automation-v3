"""A script as cards: the pieces an editor edits one at a time

A script's text is cut into cards, in order:

- "prose": a section of prose, from its heading (or the start of the
  prose) up to the next heading or directive;
- "rvt": one rvt directive, which is edited as its fields (title,
  definitions, table, variations) and its code, never as a directive;
- "variant": an rvt-variant directive, which holds cards of its own
  (`children`), cut from its content; its `variations` is a field;
- "source": an rvt or rvt-variant directive docutils can't read, edited
  as the rst it is.

Each card keeps its `source`, the exact text it was cut from, trailing
blank lines included, so the cards' sources joined are the file, byte
for byte. `build` makes a file's text from cards: a card that wasn't
edited gives back its source untouched, an edited or new one is written
fresh, and only the blank lines between a fresh card and its neighbours
are adjusted. A variant is fresh when anything inside it changed: it is
written again, its children built as a file of their own and indented.

A card's `line`, `code_line` and `code_indent` are where it is in the
file, also for the children of a variant; `indent` is how far the
lines of its `source` are indented there (a variant's children are cut
from its content, dedented).
"""

import re
from dataclasses import dataclass, field

from docutils import nodes

from . import source

PROSE, RVT, SOURCE, VARIANT = "prose", "rvt", "source", "variant"
INDENT = "   "
BLANK_TAIL = re.compile(r"(?:[ \t]*\r?\n)*\Z")


@dataclass
class Card:
    kind: str
    source: str = None  # the exact text it was cut from; None for a fresh card
    line: int = 0  # where it starts in the file, 1-based
    index: int = None  # its place among the file's cards; None for a fresh card
    # prose and source cards
    text: str = ""  # without the trailing blank lines
    heading: str = None  # a prose card's section title
    level: int = 0  # that section's depth, 1 for the document title
    # rvt cards
    title: str = None
    definitions: bool = False
    table: bool = False
    variations: list = field(default_factory=list)
    code: str = ""
    code_line: int = 0  # the file line of the code's first line
    code_indent: int = 0  # how far the code is indented in the file
    indent: int = 0  # how far the lines of `source` are indented in the file
    # variant cards
    children: list = field(default_factory=list)
    count: int = 0  # how many children it had when it was cut
    # the rvt_block or rvt_variant it was cut from (source.py), for pages;
    # None for a fresh card
    node: object = field(default=None, compare=False, repr=False)


def without_tail(source):
    """`source` without its trailing blank lines"""
    return source[:BLANK_TAIL.search(source).start()]


def walk(found):
    """Every card, the children of variants after their variant"""
    for card in found:
        yield card
        yield from walk(card.children)


def split(text):
    """The cards of a script's text. Their sources, joined, are `text`."""
    tree = source.parse(text)
    titles = sorted((span.line, node) for node in tree.findall(nodes.title)
                    if (span := source.locate(tree, node)) is not None)
    return _cut(text, tree, 1, 0, titles)


def _cut(text, container, first, cols, titles):
    """The cards of `text`, the content of `container` (the tree, or an
    rvt-variant), whose first line is file line `first`, indented `cols`
    in the file. A directive runs from its first line through the blank
    lines after it; prose is cut again at each title."""
    lines = text.splitlines(keepends=True)
    found, at = [], 0
    for block in source.blocks(container):
        start = block.line_start - first
        end = block.line_end - first + 1
        while end < len(lines) and not lines[end].strip():
            end += 1
        if "".join(lines[at:start]).strip():
            found += _prose(lines[at:start], first + at, cols, titles)
            at = start
        # else: blank lines before the file's first directive stay with it
        found.append(_directive(block, "".join(lines[at:end]), first + at, cols, titles))
        at = end
    if at < len(lines):
        found += _prose(lines[at:], first + at, cols, titles)
    for index, card in enumerate(found):
        card.index = index
    return found


def _prose(lines, start, cols, titles):
    """Prose `lines` (with line ends), from file line `start`, as cards:
    one from each title (its overline, if it has one) to the next"""
    cuts = []
    for line, title in titles:
        i = line - start
        if 0 <= i < len(lines) - 1:
            under = lines[i + 1].strip()
            if i > 0 and lines[i - 1].strip() == under:  # an overline
                i -= 1
            cuts.append((i, lines[line - start].strip(), _level(title)))
    if not cuts or "".join(lines[:cuts[0][0]]).strip():
        cuts.insert(0, (0, None, 0))
    else:  # blank lines before the first heading stay with it
        cuts[0] = (0,) + cuts[0][1:]
    found = []
    for n, (at, heading, level) in enumerate(cuts):
        end = cuts[n + 1][0] if n + 1 < len(cuts) else len(lines)
        text = "".join(lines[at:end])
        found.append(Card(PROSE, text, start + at, text=without_tail(text), heading=heading,
                          level=level, indent=cols))
    return found


def _level(title):
    """A title's depth, from the sections around it: 1 for the
    document's title"""
    depth, node = 0, title.parent
    while node is not None:
        depth += isinstance(node, nodes.section)
        node = node.parent
    return depth


def _directive(block, text, line, cols, titles):
    """The card of one rvt or rvt-variant directive: its fields, or a
    source card when it has problems"""
    if block.problems:
        return Card(SOURCE, text, line, text=without_tail(text), indent=cols)
    if isinstance(block, source.rvt_variant):
        children = _cut(block.content, block, block.content_line or line, block.indent,
                        titles)
        return Card(VARIANT, text, line, variations=list(block.variations),
                    children=children, count=len(children), indent=cols, node=block)
    return Card(RVT, text, line, title=block.title, definitions=block.is_definitions,
                table=block.is_table, variations=list(block.own_variations or []),
                code=block.code, code_line=block.content_offset + 1,
                code_indent=block.indent, indent=cols, node=block)


def rvt_source(card):
    """The rvt directive of a card's fields, ending with one line end"""
    title = " ".join((card.title or "").split())
    lines = [f".. rvt:: {title}" if title else ".. rvt::"]
    if card.definitions:
        lines.append(f"{INDENT}:definitions:")
    if card.table:
        lines.append(f"{INDENT}:table:")
    names = [name.strip() for name in card.variations if name.strip()]
    if names:
        lines.append(f"{INDENT}:variations: {', '.join(names)}")
    code = [f"{INDENT}{line}" if line.strip() else ""
            for line in card.code.strip("\n").splitlines()]
    if code:
        lines += [""] + code
    return "\n".join(lines) + "\n"


def variant_source(card):
    """The rvt-variant directive of a card's variations and children,
    ending with one line end"""
    return _variant(card)[0]


VARIANT_HEAD = 3  # lines before a variant written again starts its children


def _variant(card):
    """(variant_source, the places of what it holds: see _placed)"""
    names = [name.strip() for name in card.variations if name.strip()]
    lines = [".. rvt-variant::", f"{INDENT}:variations: {', '.join(names)}".rstrip()]
    body, inner = _placed(card.children, card.count)
    body = body.rstrip("\n")
    if body:
        lines += [""] + [f"{INDENT}{line}" if line.strip() else ""
                         for line in body.splitlines()]
    moved = {key: place.moved(VARIANT_HEAD, len(INDENT)) for key, place in inner.items()}
    return "\n".join(lines) + "\n", moved


def written(card):
    """A fresh card's text in the file, ending with one line end"""
    if card.kind == RVT:
        return rvt_source(card)
    if card.kind == VARIANT:
        return variant_source(card)
    return card.text.strip("\n") + "\n"


@dataclass(frozen=True)
class Place:
    """Where a card is in the text `build` makes, lines counted from 0:
    it covers lines `start` to `end` (not included), and the first line
    of what its editor holds (a block's code, a section's text) is line
    `code_start`, indented `code_indent` columns. `code_start` can be
    before `start`: a fresh card's leading blank lines aren't written."""

    start: int
    end: int
    code_start: int
    code_indent: int

    def moved(self, lines, cols):
        return Place(self.start + lines, self.end + lines, self.code_start + lines,
                     self.code_indent + cols)


def build(cards, original_count=None):
    """The file text of `cards`. A card with a `source` goes in as it
    is; a card without one (fresh: edited or new) is written from its
    fields. `original_count` is how many cards the file had when it was
    split (default: the highest index here, plus one), which says
    whether a kept card was the file's last."""
    return _placed(cards, original_count)[0]


def placed(cards, original_count=None):
    """(build's text, the Place of each card in it), the places in the
    order of walk(cards); None for a card that isn't in the text (a
    fresh section with no text)"""
    text, found = _placed(cards, original_count)
    return text, [found.get(id(card)) for card in walk(cards)]


def _leading(text):
    return len(text) - len(text.lstrip("\n"))


def _placed(cards, original_count=None):
    """(build's text, {id(card): Place} for the cards in it and the
    cards inside them)"""
    cards = [c for c in cards
             if c.source is not None or c.kind in (RVT, VARIANT) or c.text.strip()]
    if original_count is None:
        original_count = max((c.index for c in cards if c.index is not None), default=-1) + 1
    pieces, found, at = [], {}, 0
    for n, card in enumerate(cards):
        fresh = card.source is None
        inner = {}
        if fresh and card.kind == VARIANT:
            piece, inner = _variant(card)
        else:
            piece = written(card) if fresh else card.source
        last = n == len(cards) - 1
        if last:
            was_last = not fresh and card.index == original_count - 1
            if not was_last:
                piece = without_tail(piece) + "\n"
        else:
            after = cards[n + 1]
            follows = (not fresh and after.source is not None
                       and card.index is not None and after.index == card.index + 1)
            if not follows:  # a new neighbour: exactly one blank line between
                piece = without_tail(piece) + "\n\n"
        pieces.append(piece)
        end = at + piece.count("\n") + (0 if piece.endswith("\n") else 1)
        if fresh:
            found[id(card)] = _fresh_place(card, at, end)
            found.update({key: place.moved(at, 0) for key, place in inner.items()})
        else:
            found.update(_kept_places(card, at, end))
        at += piece.count("\n")
    return "".join(pieces), found


def _fresh_place(card, start, end):
    if card.kind == RVT:
        options = sum((card.definitions, card.table,
                       any(name.strip() for name in card.variations)))
        return Place(start, end, start + 2 + options - _leading(card.code), len(INDENT))
    if card.kind == VARIANT:
        return Place(start, end, start, 0)
    return Place(start, end, start - _leading(card.text), 0)


def _kept_places(card, start, end, cols=0):
    """{id: Place} for a card kept as it was cut, at line `start` and
    column `cols`, and for the cards inside it: where they are in its
    source, which is cut again on its own"""
    again = split(card.source)
    top = again[0] if again else None
    if top is None or top.kind != card.kind:
        return {id(card): Place(start, end, start, cols)}
    return _places_of(card, top, start, end, cols)


def _places_of(sent, cut, start, end, cols, origin=None):
    """{id: Place} for `sent` (what the page sent) and the cards inside
    it, from `cut` (the same card cut from its source, whose line 1 is
    line `origin` here, `start` by default)"""
    origin = start if origin is None else origin
    if cut.kind == RVT:
        found = {id(sent): Place(start, end, origin + cut.code_line - 1, cols + cut.code_indent)}
    else:
        found = {id(sent): Place(start, end, start, cols + cut.indent)}
    if cut.kind == VARIANT and len(sent.children) == len(cut.children):
        for child, again in zip(sent.children, cut.children):
            first = origin + again.line - 1
            found.update(_places_of(child, again, first,
                                    first + len(again.source.splitlines()), cols, origin))
    return found
