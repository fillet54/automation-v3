"""Table blocks: an rvt block's steps run once per row, in one run"""

import unittest

from automationv3.framework import document
from automationv3.framework.executor import execute_closure
from automationv3.framework.statements import get_statements

from .rvt import doc, rvt
from .test_analysis import check
from .test_compose import Recorder

ROWS = '''("a b"
  ["one"   [1 1]
   "two"   [2 3]
   "three" [3 3]])'''


def run(script):
    recorder = Recorder()
    outcome = execute_closure({"core.rst": "", "s.rst": script}, ["core.rst", "s.rst"],
                              recorder)
    return outcome, recorder


class TestRunning(unittest.TestCase):
    def test_each_row_runs_the_steps_with_its_values(self):
        outcome, rec = run(rvt(ROWS + "\n(Verify (<= a b))", "table"))
        self.assertEqual(outcome, "pass")
        self.assertEqual([(r["row"], r["values"]) for r in rec.of("row_start")],
                         [("one", {"a": "1", "b": "1"}), ("two", {"a": "2", "b": "3"}),
                          ("three", {"a": "3", "b": "3"})])
        self.assertEqual([s["row"] for s in rec.of("step_end")], ["one", "two", "three"])

    def test_a_failing_row_stops_itself_and_the_rest_still_run(self):
        script = doc(rvt(ROWS + "\n(Verify a = b)\n(Wait 1)", "table"), rvt("(Wait 9)"))
        outcome, rec = run(script)
        self.assertEqual(outcome, "fail")
        self.assertEqual([(r["row"], r["outcome"]) for r in rec.of("row_end")],
                         [("one", "pass"), ("two", "fail"), ("three", "pass")])
        steps = [(s["row"], s["passed"]) for s in rec.of("step_end")]
        self.assertEqual(steps, [("one", True), ("one", True), ("two", False),
                                 ("three", True), ("three", True)])

    def test_an_error_beats_a_failure(self):
        script = rvt('("x" ["fails" [1] "errs" [0]])\n(Verify (/ 1 x) = 2)', "table")
        self.assertEqual(run(script)[0], "error")

    def test_row_symbols_are_only_bound_inside(self):
        script = doc(rvt(ROWS + "\n(Wait a)", "table"), rvt("(Verify a = 1)"))
        self.assertEqual(run(script)[0], "error")
        errors, _ = check(script)
        self.assertTrue(any("unknown name a" in e for e in errors), errors)


class TestReading(unittest.TestCase):
    def test_parts_know_their_table(self):
        parts = [p for p in document.parse(rvt(ROWS + "\n(Wait 1)", "table")) if not p.prose]
        self.assertEqual([p.table_rows for p in parts], [True, False])
        self.assertEqual(parts[0].table, parts[1].table)

    def test_rows_render_as_a_table(self):
        rows, _ = get_statements(rvt(ROWS + "\n(Wait 1)", "table"))
        self.assertIn("<caption>For each row</caption>", rows.html)
        self.assertIn(">two</span></td>", rows.html)

    def test_the_check_knows_row_symbols_and_shapes(self):
        self.assertEqual(check(rvt(ROWS + "\n(Verify a = b)", "table")), ([], []))
        (error,) = check(rvt("(Wait 1)", "table"))[0]
        self.assertIn("a :table: block starts with its rows", error)
        (error,) = check(rvt(ROWS + "\n(def x 1)", "table"))[0]
        self.assertIn("def can't be in a :table: block", error)
        (error,) = check(rvt('("a b" ["one" [1]])', "table"))[0]
        self.assertIn("row one needs 2 values", error)


if __name__ == "__main__":
    unittest.main()
