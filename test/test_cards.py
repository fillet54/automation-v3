import unittest
from dataclasses import replace
from pathlib import Path

from automationv3.framework import cards
from automationv3.framework.cards import Card, PROSE, RVT, SOURCE

SCRIPT = """\
================
Brake Monitoring
================
Checks the brake pressure stays under the limit.

Requirements
------------
1. :req:`VMCBRA00001`

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
        files = [p for folder in ("test/data", "demo", "docs") for p in (root / folder).rglob("*.rst")]
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
            (PROSE, "Steps", 2), (RVT, None, 0), (SOURCE, None, 0), (PROSE, "Notes", 3)])
        self.assertEqual([c.index for c in found], list(range(7)))
        self.assertEqual([c.line for c in found], [1, 6, 10, 15, 20, 28, 37])

    def test_prose_text_has_no_trailing_blank_lines(self):
        found = cards.split(SCRIPT)
        self.assertEqual(found[1].text, "Requirements\n------------\n1. :req:`VMCBRA00001`")
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

    def test_an_empty_rvt_card(self):
        self.assertEqual(cards.build([Card(RVT)]), ".. rvt::\n")
        self.assertEqual(cards.split(".. rvt::\n")[0].kind, RVT)

    def test_a_new_card_gets_a_blank_line_either_side(self):
        found = cards.split("Title\n=====\nBody.\n.. rvt::\n\n   (a)\n")
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


if __name__ == "__main__":
    unittest.main()
