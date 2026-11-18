import unittest
from dataclasses import replace
from pathlib import Path

from automationv3.framework import cards
from automationv3.framework.cards import Card, PROSE, RVT, SOURCE, VARIANT

SCRIPT = """\
================
Brake Monitoring
================
Checks the brake pressure stays under the limit.

Requirements
------------
1. :req:`LGC-GDN-001`

.. rvt::
   :definitions:

   (def target 60)

Steps
-----

Apply and check.

.. rvt:: Apply the brakes fully
   :variations: degraded, limp-home

   (set-reading :brake-pressure target)

   (Verify (reading :brake-pressure) <= max-pressure)


.. rvt-variant::
   :variations: emergency

   In emergency mode the pressure stays at the limit.

   .. rvt::

      (Verify 1 = 1)

Notes
~~~~~
Done.
"""


def fresh(card, **changes):
    """`card` as the editor sends an edited one: no source"""
    return replace(card, source=None, **changes)


class TestSplit(unittest.TestCase):
    def test_the_sources_joined_are_the_file(self):
        for text in (SCRIPT, "\n\n" + SCRIPT, SCRIPT.rstrip("\n"), SCRIPT.replace("\n", "\r\n"),
                     ".. rvt::\n\n   (a)\n", "\n.. rvt::\n\n   (a)", "just prose", ""):
            self.assertEqual("".join(c.source for c in cards.split(text)), text)

    def test_every_rst_file_in_the_repository_round_trips(self):
        root = Path(__file__).parent.parent
        files = [p for folder in ("automationv3/examples", "docs") for p in (root / folder).rglob("*.rst")]
        self.assertTrue(files)
        for path in files:
            text = path.read_text()
            found = cards.split(text)
            self.assertEqual("".join(c.source for c in found), text, path)
            self.assertEqual(cards.build(found), text, path)

    def test_kinds_and_headings(self):
        found = cards.split(SCRIPT)
        self.assertEqual([(c.kind, c.heading, c.level) for c in found], [
            (PROSE, "Brake Monitoring", 1), (PROSE, "Requirements", 2), (RVT, None, 0),
            (PROSE, "Steps", 2), (RVT, None, 0), (VARIANT, None, 0), (PROSE, "Notes", 3)])
        self.assertEqual([c.index for c in found], list(range(7)))
        self.assertEqual([c.line for c in found], [1, 6, 10, 15, 20, 28, 37])

    def test_prose_text_has_no_trailing_blank_lines(self):
        found = cards.split(SCRIPT)
        self.assertEqual(found[1].text, "Requirements\n------------\n1. :req:`LGC-GDN-001`")
        self.assertEqual(found[3].text, "Steps\n-----\n\nApply and check.")

    def test_rvt_fields(self):
        found = cards.split(SCRIPT)
        definitions, steps = found[2], found[4]
        self.assertTrue(definitions.definitions)
        self.assertEqual(definitions.code, "(def target 60)")
        self.assertEqual((definitions.code_line, definitions.code_indent), (13, 3))
        self.assertEqual(steps.title, "Apply the brakes fully")
        self.assertEqual(steps.variations, ["degraded", "limp-home"])
        self.assertEqual(steps.code, "(set-reading :brake-pressure target)\n\n"
                                     "(Verify (reading :brake-pressure) <= max-pressure)")

    def test_a_variant_holds_cards(self):
        variant = cards.split(SCRIPT)[5]
        self.assertEqual((variant.variations, variant.count), (["emergency"], 2))
        prose, block = variant.children
        self.assertEqual((prose.kind, prose.line, prose.indent, prose.text),
                         (PROSE, 31, 3, "In emergency mode the pressure stays at the limit."))
        self.assertEqual((block.kind, block.line, block.code_line, block.code_indent, block.code),
                         (RVT, 33, 35, 6, "(Verify 1 = 1)"))
        self.assertEqual([c.kind for c in cards.walk([variant])], [VARIANT, PROSE, RVT])

    def test_an_unreadable_variant_is_a_source_card(self):
        (card,) = cards.split(".. rvt-variant::\n\n   Words.\n")  # no :variations:
        self.assertEqual(card.kind, SOURCE)

    def test_an_unreadable_rvt_is_a_source_card(self):
        (card,) = cards.split(".. rvt::\n   :nonsense: 1\n\n   (a)\n")
        self.assertEqual(card.kind, SOURCE)

    def test_prose_before_the_first_heading_is_a_card(self):
        found = cards.split("Intro.\n\nTitle\n=====\nBody.\n")
        self.assertEqual([(c.heading, c.text) for c in found],
                         [(None, "Intro."), ("Title", "Title\n=====\nBody.")])

    def test_not_headings(self):
        text = ("A paragraph\nthat goes on\n-----\n\n"  # underline after two lines
                "::\n\n   Indented\n   --------\n\n"
                "Short\n--\n")  # underline too short
        self.assertEqual(len(cards.split(text)), 1)

    def test_a_short_underline_of_four_or_more_is_a_heading(self):
        # as docutils, and so the page, reads it (with a warning)
        found = cards.split("Intro.\n\nHello there\n----\n\nText.\n")
        self.assertEqual([c.heading for c in found], [None, "Hello there"])

    def test_a_directive_without_a_blank_line_before_it_is_prose(self):
        # docutils reads it as the paragraph's text; source.unreadable
        # reports it, so it can't silently not run
        (card,) = cards.split("Title\n=====\nBody.\n.. rvt::\n\n   (a)\n")
        self.assertEqual(card.kind, PROSE)


class TestBuild(unittest.TestCase):
    def test_untouched_cards_build_the_same_file(self):
        self.assertEqual(cards.build(cards.split(SCRIPT)), SCRIPT)

    def test_an_edited_prose_card_changes_only_its_lines(self):
        found = cards.split(SCRIPT)
        found[3] = fresh(found[3], text="Steps\n-----\n\nApply, then check.\n\n\n")
        self.assertEqual(cards.build(found), SCRIPT.replace("Apply and check.", "Apply, then check."))

    def test_an_edited_rvt_card_is_written_from_its_fields(self):
        found = cards.split(SCRIPT)
        found[2] = fresh(found[2], definitions=False, title="Set  up", variations=["a", " b "],
                         code="(def target 70)\n\n(def other 1)\n")
        self.assertIn("\n.. rvt:: Set up\n   :variations: a, b\n\n   (def target 70)\n\n"
                      "   (def other 1)\n\nSteps\n", cards.build(found))

    def test_an_rvt_card_round_trips_through_its_fields(self):
        found = cards.split(SCRIPT)
        again = cards.split(cards.build([fresh(c) if c.kind == RVT else c for c in found]))
        for before, after in zip(found, again):
            self.assertEqual((before.kind, before.title, before.definitions, before.variations,
                              before.code), (after.kind, after.title, after.definitions,
                                             after.variations, after.code))

    def test_a_variant_with_a_changed_child_is_written_again(self):
        found = cards.split(SCRIPT)
        variant = found[5]
        block = fresh(variant.children[1], code="(Verify 2 = 2)")
        found[5] = fresh(variant, variations=["emergency", "limp-home"],
                         children=[variant.children[0], block])
        self.assertEqual(cards.build(found), SCRIPT.replace(
            ":variations: emergency\n", ":variations: emergency, limp-home\n").replace(
            "(Verify 1 = 1)", "(Verify 2 = 2)").replace(  # one blank line next to a rewritten card
            "\n\n\n.. rvt-variant", "\n\n.. rvt-variant"))

    def test_a_new_variant_around_a_card(self):
        found = cards.split("Title\n=====\nBody.\n\n.. rvt::\n\n   (a)\n")
        found[1:] = [Card(VARIANT, variations=["x"], children=[found[1]])]
        text = cards.build(found)
        self.assertEqual(text, "Title\n=====\nBody.\n\n.. rvt-variant::\n   :variations: x\n\n"
                               "   .. rvt::\n\n      (a)\n")
        (variant,) = cards.split(text)[1:]
        self.assertEqual((variant.kind, variant.children[0].code), (VARIANT, "(a)"))

    def test_an_empty_rvt_card(self):
        self.assertEqual(cards.build([Card(RVT)]), ".. rvt::\n")
        self.assertEqual(cards.split(".. rvt::\n")[0].kind, RVT)

    def test_a_new_card_gets_a_blank_line_either_side(self):
        found = cards.split("Title\n=====\nBody.\n\n.. rvt::\n\n   (a)\n")
        found.insert(1, Card(PROSE, text="New words."))
        self.assertEqual(cards.build(found),
                         "Title\n=====\nBody.\n\nNew words.\n\n.. rvt::\n\n   (a)\n")

    def test_a_new_last_card(self):
        found = cards.split("Title\n=====\nBody.")
        found.append(Card(RVT, code="(a)"))
        self.assertEqual(cards.build(found), "Title\n=====\nBody.\n\n.. rvt::\n\n   (a)\n")

    def test_deleting_the_last_card_leaves_one_line_end(self):
        found = cards.split(SCRIPT)
        self.assertTrue(cards.build(found[:-1], len(found)).endswith("      (Verify 1 = 1)\n"))

    def test_moved_cards_are_separated(self):
        found = cards.split("AA\n==\na\n\n\nBB\n==\nb\n")
        self.assertEqual(cards.build([found[1], found[0]]), "BB\n==\nb\n\nAA\n==\na\n")

    def test_an_emptied_prose_card_is_dropped(self):
        found = cards.split("AA\n==\na\n\nBB\n==\nb\n")
        self.assertEqual(cards.build([found[0], fresh(found[1], text=" \n")], 2), "AA\n==\na\n")


NESTED = """\
Title
=====

.. rvt-variant::
   :variations: a, b

   Outer words.

   .. rvt-variant::
      :variations: a

      Inner words.

      .. rvt:: Inner
         :definitions:

         (def x 1)

   .. rvt::

      (Verify 1 = 1)

Tail.
"""


def where(text):
    """(start, code start, code indent) of each card of `text`, in walk
    order, from split's own positions (lines from 0)"""
    return [(c.line - 1, c.code_line - 1, c.code_indent) if c.kind == RVT
            else (c.line - 1, c.line - 1, c.indent)
            for c in cards.walk(cards.split(text))]


def freshened(found, deep=True, kinds=(PROSE, RVT, SOURCE, VARIANT)):
    """`found` as edited: every card of `kinds` fresh, inside variants too
    when `deep`"""
    return [fresh(c, children=freshened(c.children, deep, kinds) if deep else c.children)
            if c.kind in kinds else
            replace(c, children=freshened(c.children, deep, kinds) if deep else c.children)
            for c in found]


class TestPlaced(unittest.TestCase):
    def check(self, sent, count=None):
        text, places = cards.placed(sent, count)
        self.assertEqual(text, cards.build(sent, count))
        self.assertEqual([(p.start, p.code_start, p.code_indent) for p in places], where(text))
        for place in places:
            self.assertLessEqual(place.start, place.code_start)
            self.assertLess(place.code_start, max(place.end, place.start + 1))
        return text, places

    def test_kept_cards_are_where_split_found_them(self):
        for text in (SCRIPT, NESTED):
            found = cards.split(text)
            self.assertEqual(self.check(found)[0], text)

    def test_fresh_cards(self):
        for text in (SCRIPT, NESTED):
            self.check(freshened(cards.split(text)))

    def test_a_fresh_variant_around_kept_cards(self):
        for text in (SCRIPT, NESTED):
            self.check(freshened(cards.split(text), deep=False, kinds=(VARIANT,)))

    def test_a_kept_variant_inside_a_fresh_one(self):
        outer = cards.split(NESTED)[1]
        inner = outer.children[1]
        edited = fresh(outer, children=[outer.children[0], inner, fresh(outer.children[2])])
        found = cards.split(NESTED)
        self.check([found[0], edited, found[2]], len(found))

    def test_only_blocks_edited(self):
        for text in (SCRIPT, NESTED):
            self.check(freshened(cards.split(text), kinds=(RVT,)), len(cards.split(text)))

    def test_the_leading_blank_lines_of_a_fresh_card_are_before_it(self):
        found = cards.split(SCRIPT)
        sent = [found[0], fresh(found[1], text="\n\nRequirements\n------------\nNone.")]
        text, places = cards.placed(sent + found[2:], len(found))
        self.assertEqual(places[1].code_start, places[1].start - 2)
        self.assertEqual(text.splitlines()[places[1].start], "Requirements")
        sent = [fresh(found[2], code="\n(def target 60)")]
        text, places = cards.placed(sent)
        self.assertEqual(text.splitlines()[places[0].code_start + 1], "   (def target 60)")

    def test_a_dropped_card_has_no_place(self):
        found = cards.split("AA\n==\na\n\nBB\n==\nb\n")
        self.assertEqual(cards.placed([found[0], fresh(found[1], text=" ")], 2)[1][1], None)


if __name__ == "__main__":
    unittest.main()
