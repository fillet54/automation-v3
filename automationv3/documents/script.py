"""A script as one reStructuredText document, with or without a run

A page follows the script's cards (framework/cards.py), each read from
the one tree of the script (framework/source.py):

- prose as written, at the top level, so its headings are the page's
  sections;
- each rvt block in a ``block`` container: a titled block is
  ``block titled collapsible`` (its title is the summary), the
  definitions section ``block definitions collapsible``, any other
  block holds its steps as they are. Inside, each step is in a ``step``
  container, a definition elsewhere and a precondition in
  ``collapsible`` ones (the first paragraph is their summary). A block
  limited to variations of its own is wrapped in a ``scoped`` container;
- an rvt-variant is a ``scoped variant`` container holding its cards.

With `results`, each step is followed by the directive its result
resolves from (see run.py), so the same document is a script's page
before it runs and a run's page after: a run page shows the script's
cards, each with its steps' results in it, filled in as the run goes.

For one variation, what that variation doesn't run is left out, and the
definitions section is rolled up into one: each name's last definition
that applies (the one that wins), where the first definitions block is.
"""

import functools
from dataclasses import dataclass

from ..framework import cards as card_model
from ..framework import source as script_source
from ..framework.block import is_placeholder
from ..framework.language import (
    PRECONDITION, head, is_definition, is_step, parse_precondition,
)
from ..framework.rst import repr_rst
from . import core
from .template import Rst, indent, literal, text


@dataclass
class View:
    """A statement as pages and snippets show it: its rst, and for a
    Precondition its name, its heal's description, and its check and
    heal as rst on their own"""

    statement: script_source.Statement
    rst: str
    precondition: dict = None

    @property
    def form(self):
        return self.statement.form


def view(statement):
    """The View of a source.Statement"""
    form = statement.form
    found = View(statement, repr_rst(form))
    parsed = head(form) == PRECONDITION and parse_precondition(form)
    if parsed:
        found.precondition = {
            "name": parsed.name,
            "heal_name": parsed.heal_name,
            "check_rst": repr_rst(parsed.check),
            "heal_rst": repr_rst(parsed.heal) if parsed.heal is not None else None,
        }
    return found


def defines(form):
    """The name a definition binds, else None"""
    return str(form[1]) if is_definition(form) else None


def block(classes, summary, body):
    """A container: `summary` first (for collapsible ones), then `body`"""
    parts = [summary] if summary else []
    parts += [b for b in body if b]
    inner = "\n\n".join(indent(Rst(p), 3, first=True) for p in parts)
    return Rst(f".. container:: {classes}\n\n{inner}\n")


def diagnostic(d):
    lines = [f".. container:: diagnostic {d.get('severity', 'error')}", "",
             f"   **{text(str(d.get('severity', 'error')).capitalize())}** {text(d['message'])}"]
    excerpt = d.get("excerpt")
    if excerpt:
        from .run import excerpt_rst
        lines += ["", "   ::", "", indent(excerpt_rst(excerpt), 6, first=True)]
    return Rst("\n".join(lines) + "\n")


def applies(variations, variation):
    return variation is None or not variations or variation in variations


class Writer:
    """Writes cards as page rst (see the module docs)"""

    def __init__(self, statements, variation=None, results=False, diagnostics=(),
                 variations=True):
        self.variation, self.results = variation, results
        self.diagnostics, self.variations = diagnostics, variations
        self.of_block = {}
        for statement in statements:
            self.of_block.setdefault(statement.block.key, []).append(statement)
        self.rolled = self.first = None
        if variation is not None:
            section = [s for s in statements if s.definitions and s.applies(variation)]
            last = {defines(s.form): s for s in section}
            self.rolled = [s for s in section if last[defines(s.form)] is s]
            first_block = next((s.block for s in statements if s.definitions), None)
            self.first = first_block.key if first_block is not None else None

    def cards(self, found):
        return "\n\n".join(p for p in (self.card(c) for c in found) if p)

    def card(self, card):
        if card.kind == card_model.VARIANT:
            return self.variant(card)
        if card.kind == card_model.RVT:
            return self.block(card.node)
        return card.text

    def variant(self, card):
        names = card.node.variations
        if not applies(names, self.variation):
            return ""
        body = self.cards(card.children)
        only = " ".join(literal(v) for v in names)
        return block("scoped variant", f"*Only for* {only}", [body]) if body else ""

    def block(self, node):
        if not applies(node.variations, self.variation):
            return ""
        found = self.of_block.get(node.key, [])
        definitions = node.is_definitions
        if definitions and self.rolled is not None:
            if node.key != self.first:
                return ""
            found = self.rolled
        shown = [(s, self.item(s)) for s in found]
        shown = [(s, rst) for s, rst in shown if rst]
        if not shown:
            return ""
        if definitions:
            names = ", ".join(n for n in (defines(s.form) for s, _ in shown) if n)
            written = block("block definitions collapsible",
                            f"**Definitions** {literal(names) if names else ''}",
                            [rst for _, rst in shown])
        else:
            entries = [self.definition(s, rst) if is_definition(s.form) else rst
                       for s, rst in shown]
            if node.title:
                covered = [s.index for s, _ in shown]
                state = (f" :run-state:`{min(covered)}-{max(covered)}`" if self.results else "")
                todo = (" :verdict:`tbd`" if not self.results
                        and any(is_placeholder(s.form) for s, _ in shown) else "")
                written = block("block titled collapsible",
                                f"**{text(node.title)}**{state}{todo}", entries)
            else:
                written = block("block", None, entries)
        own = node.own_variations
        if own and not (definitions and self.rolled is not None):
            only = " ".join(literal(v) for v in own)
            written = block("scoped", f"*Only for* {only}", [written])
        return written

    @staticmethod
    def definition(statement, rst):
        return block("definition collapsible",
                     f"**Definition** {literal(defines(statement.form))}", [rst])

    def item(self, statement):
        """A statement's rst, or "" when this page leaves it out"""
        form, index = statement.form, statement.index
        if not self.variations and head(form) == "variations":
            return ""
        if self.results and statement.table is not None and not statement.table_rows:
            return ""  # the rows' results show its steps
        shown = view(statement)
        parts = []
        if not is_step(form):
            parts.append(shown.rst)
            if self.results and is_definition(form):
                parts.append(f".. step-result:: {index}\n   :ended-only:\n")
        elif shown.precondition:
            p = shown.precondition
            summary = (f"**Precondition** {text(p['name'])}"
                       + (" *(heals)*" if p.get("heal_rst") else "")
                       + (f" :run-state:`{index}`" if self.results else ""))
            if self.results:
                body = [f".. precondition-result:: {index}"]
            else:
                body = ["**Check**", p["check_rst"]]
                if p.get("heal_rst"):
                    body += [f"**If not, heal by** {text(p.get('heal_name') or '')}",
                             p["heal_rst"]]
            parts.append(block("precondition collapsible", summary, body))
        elif statement.table_rows:
            parts.append(shown.rst)
            if self.results:
                parts.append(f".. table-results:: {index}")
        else:
            parts.append(block("step", None, [shown.rst,
                               f".. step-result:: {index}" if self.results else ""]))
        parts += [diagnostic(d) for d in self.own(statement)]
        return "\n\n".join(parts)

    def own(self, statement):
        """The diagnostics about lines `statement` covers, each marked
        "inline" (it shows by its statement)"""
        span = statement.span
        found = [d for d in self.diagnostics if span is not None and d.get("line") is not None
                 and span.line <= d["line"] <= span.end_line]
        for d in found:
            d["inline"] = True
        return found


def render(text_, found=None, variation=None, results=False, diagnostics=(), variations=True):
    """The page rst of cards of a script's text: `found` (cut from it by
    cards.split), or all of them. Raises ValueError if a block can't be
    read."""
    tree = script_source.parse(text_)
    problems = script_source.unreadable(tree)
    if problems:
        raise ValueError(problems[0].message)
    found = card_model.split(text_) if found is None else found
    writer = Writer(script_source.statements(tree), variation, results, diagnostics, variations)
    return writer.cards(found)


@functools.lru_cache(maxsize=64)
def _parsed(text_, variation, results, variations):
    return core.parse(render(text_, None, variation, results, (), variations),
                      source_path="<script>")


def parsed(text_, variation=None, results=False, diagnostics=(), variations=True):
    """The parsed (unresolved) document of a script's text: cached, unless
    it carries diagnostics"""
    if diagnostics:
        return core.parse(render(text_, None, variation, results, diagnostics, variations),
                          source_path="<script>")
    return _parsed(text_, variation, results, variations)
