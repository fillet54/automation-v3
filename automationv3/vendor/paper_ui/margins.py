"""Margin notes for documents: what the "tufte" layout puts beside the text (docutils, so apps can use it too)

The layouts (ui.css: <html data-ui-layout="narrow|medium|full|tufte">) decide where things go; the markup only
says what they are, with two classes:

- ``ui-margin``: belongs in the margin. In the tufte layout it floats into the margin beside the text it follows;
  in the others it stays where it is, as it would without the class.
- ``ui-wide``: as wide as the page (text column and margin), where it would otherwise be as wide as the text.

Any directive with a ``:class:`` option can use them (``.. figure:: :class: ui-margin``). For what has no class
option, or none written, this module adds:

- ``.. margin::``, a block of any content in the margin (a small figure, a table, a remark);
- ``:sidenote:`text```, a numbered note written where it belongs: a footnote in every layout, beside its
  reference in the tufte layout;
- ``:marginnote:`text```, the same unnumbered (a symbol footnote elsewhere);
- ``apply(doctree)``, after footnotes are resolved: a copy of each footnote's text after its reference
  (span.ui-sidenote, shown only by the tufte layout, the footnotes at the end by the others), and the
  ``ui-margin`` class on the kinds of element that go in the margin (sidebars, version notes, notes...).

Sphinx: the "paper" theme does all of this (paper_ui.sphinx). docutils on its own::

    from paper_ui import margins
    margins.register()                                  # once: the directive and the roles
    tree = docutils.core.publish_doctree(text)
    margins.apply(tree)                                 # before writing it
"""

import copy

from docutils import nodes
from docutils.parsers.rst import Directive, directives, roles
from docutils.transforms import Transform

# what goes in the margin unless a project says otherwise: node names (a sidebar, Sphinx's version notes) and
# admonition kinds; warnings and the like stay in the text, where they can't be missed
MARGIN = ("sidebar", "versionmodified", "note", "tip", "hint", "seealso")


def kinds(value):
    """MARGIN from a theme option or setting: "sidebar, note" (or a list); "none" or empty for none"""
    if value is None:
        return set(MARGIN)
    if isinstance(value, str):
        value = value.replace(",", " ").split()
    return {v.strip().lower() for v in value if v.strip() and v.strip().lower() != "none"}


# ---------------------------------------------------------------------------------------------- markup

class Margin(Directive):
    """.. margin:: — its content in the margin (in the text, ruled, in the layouts without one)"""
    has_content = True
    optional_arguments = 0
    option_spec = {"class": directives.class_option, "name": directives.unchanged}

    def run(self):
        self.assert_has_content()
        node = nodes.container("\n".join(self.content), classes=["ui-margin", "ui-margin-note"])
        node["classes"] += self.options.get("class", [])
        self.add_name(node)
        self.state.nested_parse(self.content, self.content_offset, node)
        return [node]


class PlaceNotes(Transform):
    """Puts the footnotes the roles made at the end of the document (or of its one top section), and only then
    tells docutils about the numbered ones, so they are numbered after the document's own footnotes"""
    default_priority = 610      # docutils numbers and resolves footnotes at 620

    def apply(self):
        pending = getattr(self.document, "_paper_notes", [])
        if not pending:
            return
        sections = [c for c in self.document.children if isinstance(c, nodes.section)]
        target = sections[-1] if len(sections) == 1 else self.document
        for footnote in pending:
            target.append(footnote)
            if footnote.get("auto") == 1:
                self.document.note_autofootnote(footnote)
                self.document.note_explicit_target(footnote, footnote)
        self.document._paper_notes = []


# symbols for unnumbered notes in the layouts that show them as footnotes, as docutils uses them
SYMBOLS = ["*", "\u2020", "\u2021", "\u00a7", "\u00b6", "#", "\u2660", "\u2665", "\u2666", "\u2663"]


def note_role(numbered):
    """:sidenote: (a numbered footnote, sharing the footnotes' numbers) and :marginnote: (a footnote marked
    with a symbol; the tufte layout shows it without one)"""

    def role(name, rawtext, text, lineno, inliner, options=None, content=None):
        document = inliner.document
        body, messages = inliner.parse(text, lineno, inliner, inliner.parent)   # the inliner is its own memo
        cls = "ui-sidenote-note" if numbered else "ui-marginnote"
        footnote = nodes.footnote(rawtext, nodes.paragraph(text, "", *body), classes=[cls])
        ref = nodes.footnote_reference(rawtext, classes=[cls + "-ref"])
        if numbered:
            count = getattr(document, "_paper_note_count", 0) + 1
            document._paper_note_count = count
            label = f"paper-note-{count}"
            footnote["auto"] = ref["auto"] = 1
            footnote["names"].append(label)
            ref["refname"] = label
            document.note_autofootnote_ref(ref)
            document.note_footnote_ref(ref)
        else:
            # resolved here, not by docutils' symbol footnotes, which pair references and notes by their order
            count = getattr(document, "_paper_margin_count", 0)
            document._paper_margin_count = count + 1
            symbol = SYMBOLS[count % len(SYMBOLS)] * (count // len(SYMBOLS) + 1)
            document.set_id(ref)
            document.set_id(footnote)
            ref["refid"] = footnote["ids"][0]
            footnote["backrefs"] = [ref["ids"][0]]
            ref += nodes.Text(symbol)
            footnote.insert(0, nodes.label("", symbol))
        if not hasattr(document, "_paper_notes"):
            document._paper_notes = []
            document.transformer.add_transform(PlaceNotes)
        document._paper_notes.append(footnote)
        return [ref], messages

    return role


sidenote_role = note_role(numbered=True)
marginnote_role = note_role(numbered=False)


def register():
    """The directive and the roles, for docutils on its own (Sphinx: the theme registers them)"""
    directives.register_directive("margin", Margin)
    roles.register_local_role("sidenote", sidenote_role)
    roles.register_local_role("marginnote", marginnote_role)


# ---------------------------------------------------------------------------------------------- the doctree

# a reference in these is left alone: a note can't float out of a table cell, a title or a caption
NO_SIDENOTE = (nodes.table, nodes.title, nodes.caption, nodes.footnote, nodes.citation, nodes.sidebar, nodes.topic)


def strip_ids(node):
    """A copy's elements without ids (the original keeps them), so anchors stay unique"""
    for n in node.findall(nodes.Element):
        n["ids"] = []
        if "backrefs" in n:
            n["backrefs"] = []
    return node


def tighten(ref):
    """reStructuredText needs a space before a role; a note's mark goes against the word before it"""
    if not any(c in ref["classes"] for c in ("ui-sidenote-note-ref", "ui-marginnote-ref")):
        return
    index = ref.parent.index(ref)
    before = ref.parent[index - 1] if index else None
    if isinstance(before, nodes.Text) and before.endswith(" "):
        ref.parent.replace(before, nodes.Text(before.rstrip(" ")))


def add_sidenotes(doctree):
    """A copy of each footnote's text right after its (first) reference: span.ui-sidenote"""
    done = set()
    for ref in list(doctree.findall(nodes.footnote_reference)):
        footnote = doctree.ids.get(ref.get("refid"))
        if footnote is None or ref["refid"] in done or not isinstance(ref.parent, nodes.TextElement):
            continue
        if any(isinstance(a, NO_SIDENOTE) for a in iter_parents(ref)):
            continue
        done.add(ref["refid"])
        margin = "ui-marginnote" in footnote["classes"]
        side = nodes.inline(classes=["ui-sidenote"] + (["ui-sidenote--unnumbered"] if margin else []))
        if not margin:
            label = next(iter(footnote.findall(nodes.label)), None)
            side += nodes.inline("", label.astext() if label else ref.astext().strip("[]"),
                                 classes=["ui-sidenote__num"])
        for child in footnote.children:
            if isinstance(child, nodes.label):
                continue
            if isinstance(child, nodes.paragraph):
                side += nodes.inline("", "", *[strip_ids(copy.deepcopy(c)) for c in child.children],
                                     classes=["ui-sidenote__p"])
            else:
                side += nodes.inline("", child.astext(), classes=["ui-sidenote__p"])
        if margin:
            ref["classes"] = sorted(set(ref["classes"]) | {"ui-marginnote-ref"})
        footnote["classes"].append("ui-has-sidenote")
        ref.parent.insert(ref.parent.index(ref) + 1, side)
    # a "Footnotes" rubric goes with them when all the footnotes after it are beside their references
    for rubric in list(doctree.findall(nodes.rubric)):
        after, following = rubric.next_node(descend=False, siblings=True), []
        while isinstance(after, nodes.footnote):
            following.append(after)
            after = after.next_node(descend=False, siblings=True)
        if following and all("ui-has-sidenote" in f["classes"] for f in following):
            rubric["classes"].append("ui-footnotes-rubric")


def iter_parents(node):
    node = node.parent
    while node is not None:
        yield node
        node = node.parent


def mark_margin(doctree, margin=None):
    """The ui-margin class on the kinds of element `margin` names (MARGIN by default)"""
    wanted = kinds(margin)
    for node in doctree.findall(nodes.Element):
        name = node.tagname.lower()
        if name in wanted or (isinstance(node, nodes.Admonition) and wanted & set(node["classes"])):
            if "ui-margin" not in node["classes"]:
                node["classes"].append("ui-margin")


def apply(doctree, margin=None, sidenotes=True):
    """Everything the tufte layout needs in a resolved doctree; the other layouts look as they would without"""
    for ref in list(doctree.findall(nodes.footnote_reference)):
        tighten(ref)
    if sidenotes:
        add_sidenotes(doctree)
    mark_margin(doctree, margin)
    return doctree
