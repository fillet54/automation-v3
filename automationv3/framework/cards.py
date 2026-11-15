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

from . import document

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


def is_adornment(line):
    return bool(document.HEADING_LINE.match(line))


def headings(lines):
    """[(index of a heading's first line, title, style)] for the section
    headings in `lines` (prose, without line ends). A heading is a line
    of text underlined with punctuation at least as long, after a blank
    line, the start, or an overline of the same punctuation."""
    found = []
    i = 0
    while i < len(lines) - 1:
        title, under = lines[i], lines[i + 1].rstrip()
        if (title.strip() and not title[0].isspace() and not is_adornment(title)
                and is_adornment(under) and len(under) >= len(title.rstrip())):
            before = lines[i - 1] if i else ""
            over = bool(i) and is_adornment(before) and before.strip()[0] == under[0]
            if over or not before.strip():
                found.append((i - 1 if over else i, title.strip(), (under[0], over)))
                i += 2
                continue
        i += 1
    return found


def chunks(text):
    """[(kind, lines, first line)] of the text's prose and directives,
    like document.split, but keeping every line, with its line end: a
    directive takes the blank lines after it, and blank lines before
    the first chunk go to it"""
    found, current, start, kind = [], [], 1, "prose"
    for line_no, line in enumerate(text.splitlines(keepends=True), start=1):
        bare = line.rstrip("\r\n")
        if kind != "prose" and bare.strip() and not bare[0].isspace():
            found.append((kind, current, start))
            current, start, kind = [], line_no, "prose"
        if kind == "prose" and (document.RVT_START.match(bare)
                                or document.VARIANT_START.match(bare)):
            if "".join(current).strip():
                found.append((kind, current, start))
                current = []
                start = line_no
            # blank lines before the file's first chunk stay with it
            kind = "rvt" if document.RVT_START.match(bare) else "variant"
        current.append(line)
    if current:
        found.append((kind, current, start))
    return found


def without_tail(source):
    """`source` without its trailing blank lines"""
    return source[:BLANK_TAIL.search(source).start()]


def prose_cards(lines, start, styles):
    """The prose `lines` (with line ends) as cards, one per heading.
    `styles` is the heading styles met so far in the document, in order:
    a style's place is its section's depth."""
    bare = [line.rstrip("\r\n") for line in lines]
    found = headings(bare)
    cuts = [at for at, _, _ in found]
    if not cuts or "".join(lines[:cuts[0]]).strip():
        cuts.insert(0, 0)
        found.insert(0, (0, None, None))
    else:  # blank lines before the first heading stay with it
        cuts[0] = 0
    cards = []
    for n, (_, title, style) in enumerate(found):
        end = cuts[n + 1] if n + 1 < len(cuts) else len(lines)
        source = "".join(lines[cuts[n]:end])
        level = 0
        if style is not None:
            if style not in styles:
                styles.append(style)
            level = styles.index(style) + 1
        cards.append(Card(PROSE, source, start + cuts[n], text=without_tail(source),
                          heading=title, level=level))
    return cards


def rvt_card(lines, start):
    """The card of one rvt directive: its fields, or a source card when
    docutils can't read it"""
    source = "".join(lines)
    lead = next(i for i, line in enumerate(lines) if line.strip())
    directive = "".join(lines[lead:])
    try:
        block = document.parse_directive(directive, document.rvt_block, "rvt")
    except document.RvtError:
        return Card(SOURCE, source, start, text=without_tail(source))
    options = block["options"]
    _, col_shift = document.content_position(directive, block["content"], block["offset"])
    return Card(RVT, source, start, title=block["title"],
                definitions="definitions" in options, table="table" in options,
                variations=list(options.get("variations") or []),
                code=block["content"], code_line=start + lead + block["offset"],
                code_indent=col_shift(0))


def variant_card(lines, start, styles):
    """The card of one rvt-variant directive, holding the cards of its
    content; or a source card when docutils can't read it"""
    source = "".join(lines)
    lead = next(i for i, line in enumerate(lines) if line.strip())
    directive = "".join(lines[lead:])
    try:
        node = document.parse_directive(directive, document.rvt_variant, "rvt-variant")
    except document.RvtError:
        return Card(SOURCE, source, start, text=without_tail(source))
    _, col_shift = document.content_position(directive, node["content"], node["offset"])
    indent = col_shift(0)
    children = split(node["content"], styles)
    moved(children, start + lead + node["offset"] - 1, indent)
    return Card(VARIANT, source, start, variations=list(node["variations"]),
                children=children, count=len(children))


def moved(found, lines, cols):
    """Move cards cut from a directive's content to where they are in the
    file: `lines` down and `cols` right"""
    for card in found:
        card.line += lines
        if card.code_line:
            card.code_line += lines
            card.code_indent += cols
        card.indent += cols
        moved(card.children, lines, cols)


def walk(found):
    """Every card, the children of variants after their variant"""
    for card in found:
        yield card
        yield from walk(card.children)


def split(text, styles=None):
    """The cards of a script's text. Their sources, joined, are `text`."""
    cards, styles = [], [] if styles is None else styles
    for kind, lines, start in chunks(text):
        if kind == "prose":
            cards += prose_cards(lines, start, styles)
        elif kind == "rvt":
            cards.append(rvt_card(lines, start))
        else:
            cards.append(variant_card(lines, start, styles))
    for index, card in enumerate(cards):
        card.index = index
    return cards


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
    names = [name.strip() for name in card.variations if name.strip()]
    lines = [".. rvt-variant::", f"{INDENT}:variations: {', '.join(names)}".rstrip()]
    body = build(card.children, card.count).rstrip("\n")
    if body:
        lines += [""] + [f"{INDENT}{line}" if line.strip() else ""
                         for line in body.splitlines()]
    return "\n".join(lines) + "\n"


def written(card):
    """A fresh card's text in the file, ending with one line end"""
    if card.kind == RVT:
        return rvt_source(card)
    if card.kind == VARIANT:
        return variant_source(card)
    return card.text.strip("\n") + "\n"


def build(cards, original_count=None):
    """The file text of `cards`. A card with a `source` goes in as it
    is; a card without one (fresh: edited or new) is written from its
    fields. `original_count` is how many cards the file had when it was
    split (default: the highest index here, plus one), which says
    whether a kept card was the file's last."""
    cards = [c for c in cards
             if c.source is not None or c.kind in (RVT, VARIANT) or c.text.strip()]
    if original_count is None:
        original_count = max((c.index for c in cards if c.index is not None), default=-1) + 1
    pieces = []
    for n, card in enumerate(cards):
        fresh = card.source is None
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
    return "".join(pieces)
