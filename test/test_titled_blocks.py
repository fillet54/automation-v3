"""Titled rvt blocks: `.. rvt:: Title` collapses the block's forms"""

import unittest

from automationv3.framework import source
from automationv3.web.reports import duration

from .rvt import doc, page_entries, rvt
from .test_definitions import run

SCRIPT = doc(
    rvt("(def limit 80)", "definitions", title="Ignored for the definitions section"),
    "Steps",
    rvt("(Verify limit = 80) (Verify limit > 0)", title="Check   the limit"),
    rvt("(Verify limit < 100)", title="Check the limit"),
    rvt("(Wait 0)"),
)


def kinds(entries):
    return [(classes, summary) for classes, summary, _ in entries]


class TestParsing(unittest.TestCase):
    def test_title_is_the_directive_argument(self):
        titles = [(s.title, s.form) for s in source.statements(source.parse(SCRIPT))]
        self.assertEqual([t for t, _ in titles], [
            "Ignored for the definitions section", "Check the limit",
            "Check the limit", "Check the limit", None])

    def test_titled_blocks_run_as_before(self):
        outcome, recorder = run(SCRIPT)
        self.assertEqual(outcome, "pass")
        self.assertEqual(len(recorder.steps()), 4)

    def test_title_with_options(self):
        script = doc(rvt('(variations "x" ["a" [1]])'),
                     rvt("(Wait 0)", title="Pause", variations="a"))
        (part,) = source.statements(source.parse(script))[1:]
        self.assertEqual((part.title, part.variations), ("Pause", ["a"]))


class TestPage(unittest.TestCase):
    def test_each_block_is_its_own_entry(self):
        entries = page_entries(SCRIPT)
        self.assertEqual(kinds(entries), [
            ("block definitions collapsible", "Definitions limit"),
            ("block titled collapsible", "Check the limit"),
            ("block titled collapsible", "Check the limit"),  # the same title, another block
            ("block", ""),                                    # untitled: its steps as they are
        ])
        self.assertEqual([c for c, _, _ in entries[1][2]], ["step", "step"])

    def test_titled_blocks_inside_a_scope(self):
        script = doc(rvt('(variations "x" ["a" [1] "b" [2]])'),
                     rvt("(Wait 0) (Wait 0)", title="Pause", variations="a"))
        classes, summary, inner = page_entries(script)[-1]
        self.assertEqual((classes, summary), ("scoped", "Only for a"))
        self.assertEqual(kinds(inner), [("block titled collapsible", "Pause")])

    def test_a_tbd_step_marks_its_block(self):
        script = doc(rvt('(Wait 0) (TBD "later")', title="Not yet"))
        (classes, summary, _), = page_entries(script)
        self.assertEqual(summary, "Not yet tbd")


class TestDurations(unittest.TestCase):
    def test_formatting(self):
        cases = [(None, ""), (0, "0 ms"), (0.0074, "7 ms"), (0.999, "999 ms"),
                 (1, "1.000 s"), (1.2345, "1.234 s"), (59.9994, "59.999 s"),
                 (125.0123, "2:05.012")]
        for seconds, text in cases:
            self.assertEqual(duration(seconds), text, seconds)


if __name__ == "__main__":
    unittest.main()
