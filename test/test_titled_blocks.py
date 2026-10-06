"""Titled rvt blocks: `.. rvt:: Title` collapses the block's forms"""

import unittest

from automationv3.framework import document
from automationv3.framework.statements import get_statements
from automationv3.web.grouping import block_state, group, statement_item

from .rvt import doc, rvt
from .test_definitions import run

SCRIPT = doc(
    rvt("(def limit 80)", "definitions", title="Ignored for the definitions section"),
    "Steps",
    rvt("(Verify limit = 80) (Verify limit > 0)", title="Check   the limit"),
    rvt("(Verify limit < 100)", title="Check the limit"),
    rvt("(Wait 0)"),
)


def kinds(entries):
    return [(kind, entry["title"] if kind == "titled" else None)
            for kind, entry in entries]


class TestParsing(unittest.TestCase):
    def test_title_is_the_directive_argument(self):
        titles = [(part.title, part.form) for part in document.parse(SCRIPT)
                  if not part.prose]
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
        (part,) = [p for p in document.parse(script) if not p.prose][1:]
        self.assertEqual((part.title, part.variations), ("Pause", ["a"]))


class TestGrouping(unittest.TestCase):
    def test_a_titled_block_is_one_entry(self):
        entries = group([statement_item(s) for s in get_statements(SCRIPT)])
        self.assertEqual(kinds(entries), [
            ("definitions", None),
            ("statement", None),        # prose
            ("titled", "Check the limit"),
            ("titled", "Check the limit"),  # the same title, another block
            ("statement", None),        # untitled: shown as it is
        ])
        self.assertEqual(len(entries[2][1]["entries"]), 2)

    def test_titled_blocks_inside_a_scope(self):
        script = doc(rvt('(variations "x" ["a" [1] "b" [2]])'),
                     rvt("(Wait 0) (Wait 0)", title="Pause", variations="a"))
        entries = group([statement_item(s) for s in get_statements(script)])
        kind, scoped = entries[-1]
        self.assertEqual(kind, "scoped")
        self.assertEqual(kinds(scoped["entries"]), [("titled", "Pause")])

    def test_block_state(self):
        def items(*states):
            return [{"step": True, "state": s} for s in states] + [{"step": False}]
        self.assertIsNone(block_state([{"step": False}]))
        self.assertEqual(block_state(items("pass", "pass")), "pass")
        self.assertEqual(block_state(items("pass", "fail", "not run")), "fail")
        self.assertEqual(block_state(items("pass", "running", "pending")), "running")
        self.assertEqual(block_state(items("not run", "not run")), "not run")
