"""Where failures happened: traces of spans, and excerpts of the code"""

import unittest

from automationv3.framework.excerpt import excerpt, failure_view, frames

from .test_compose import run

CORE_LINE_OF_VERIFY = 13  # (Verify p <= limit) inside hard-stop's step, in core.rst


def failed_step(script):
    outcome, rec = run(script)
    return outcome, rec.of("step_end")[-1]


class TestTraces(unittest.TestCase):
    def test_a_failure_inside_a_defn_points_at_the_block_then_the_call(self):
        outcome, step = failed_step("(via-defn 95)")
        self.assertEqual(outcome, "fail")
        self.assertEqual(step["message"], "(Verify p <= limit) failed: 95 <= 80")
        where = [(t["source"], t["line"]) for t in frames(step["trace"])]
        self.assertEqual(where, [("core.rst", CORE_LINE_OF_VERIFY), ("core.rst", 17),
                                 ("s.rst", 3)])

    def test_an_unknown_name_points_at_the_name(self):
        outcome, step = failed_step("(let [x 1] (Verify (+ x y) = 1))")
        self.assertEqual(outcome, "error")
        self.assertIn("raised unknown name y", step["message"])
        innermost = step["trace"][0]
        self.assertEqual((innermost["line"], innermost["col"], innermost["end_col"]),
                         (3, 27, 28))

    def test_a_direct_block_failure(self):
        _, step = failed_step("(Verify 1 = 2)")
        self.assertEqual(step["message"], "(Verify 1 = 2) failed: 1 = 2")
        self.assertEqual(step["trace"][0]["line"], 3)

    def test_passing_steps_carry_no_failure(self):
        _, rec = run("(Wait 1)")
        self.assertNotIn("message", rec.of("step_end")[0])


class TestExcerpts(unittest.TestCase):
    FILES = {"s.rst": "Title\n\n.. rvt::\n\n   (Wait 1)\n   (Verify (f x)\n           = 2)\n"}

    def span(self, line, col, end_line, end_col):
        return {"source": "s.rst", "line": line, "col": col,
                "end_line": end_line, "end_col": end_col}

    def test_marks_the_columns_and_dedents(self):
        ex = excerpt(self.FILES, self.span(6, 11, 6, 16))
        self.assertEqual(ex["where"], "s.rst:6:12")
        (before, line) = ex["rows"]
        self.assertEqual((before["no"], before["text"], before["mark"]), (5, "(Wait 1)", None))
        self.assertEqual((line["before"], line["marked"], line["after"]),
                         ("(Verify ", "(f x)", ""))

    def test_multi_line_spans_mark_each_line(self):
        ex = excerpt(self.FILES, self.span(6, 3, 7, 15))
        marked = [row["marked"] for row in ex["rows"] if row["mark"]]
        self.assertEqual(marked, ["(Verify (f x)", "= 2)"])

    def test_unknown_files_have_no_excerpt(self):
        self.assertIsNone(excerpt(self.FILES, {**self.span(1, 0, 1, 1), "source": "x"}))

    def test_failure_view_keeps_tracebacks_only(self):
        view = failure_view(self.FILES, "boom", [self.span(5, 3, 5, 11)], "plain text")
        self.assertEqual((view["message"], len(view["excerpts"]), view["traceback"]),
                         ("boom", 1, ""))


if __name__ == "__main__":
    unittest.main()
