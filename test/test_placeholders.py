"""Steps not written yet: (TBD "...")"""

import unittest

from automationv3.framework.statements import get_statements
from automationv3.services.reports import rollup

from .rvt import rvt
from .test_analysis import check
from .test_compose import run


class TestRunning(unittest.TestCase):
    def test_a_run_with_placeholders_is_incomplete(self):
        outcome, rec = run('(Wait 1) (TBD "Engage the autopilot") (Wait 2)')
        self.assertEqual(outcome, "incomplete")
        steps = rec.of("step_end")
        self.assertEqual([s["passed"] for s in steps], [True, True, True])
        self.assertEqual([s.get("placeholders", 0) for s in steps], [0, 1, 0])
        self.assertEqual(steps[1]["stdout"], "to be written")

    def test_without_placeholders_it_passes(self):
        self.assertEqual(run("(Wait 1)")[0], "pass")

    def test_a_failure_still_fails(self):
        self.assertEqual(run('(TBD "later") (Verify 1 = 2)')[0], "fail")

    def test_inside_code_it_is_a_reported_call_that_comes_out_true(self):
        outcome, rec = run('(if (TBD "Autopilot engaged?") (Wait 1) (Verify false))')
        self.assertEqual(outcome, "incomplete")
        tbd, wait = rec.calls(0)
        self.assertEqual(tbd["block_kind"], "placeholder")
        self.assertEqual(rec.of("step_end")[0]["placeholders"], 1)

    def test_a_precondition_check_holds(self):
        outcome, _ = run('(Precondition "Aircraft trimmed" (TBD "check trim")) (Wait 1)')
        self.assertEqual(outcome, "incomplete")

    def test_incomplete_runs_dont_roll_up_green(self):
        self.assertEqual(rollup.color(["pass", "incomplete"]), "partial")


class TestReading(unittest.TestCase):
    def test_renders_as_a_step_to_be_written(self):
        (statement,) = get_statements(rvt('(TBD "Engage the <autopilot>")'))
        self.assertIn("To be written", statement.html)
        self.assertIn("Engage the &lt;autopilot&gt;", statement.html)

    def test_the_check_counts_them_as_a_warning(self):
        errors, (warning,) = check(rvt('(TBD "a") (step "b" (TBD "c"))'))
        self.assertEqual(errors, [])
        self.assertIn("2 steps are still to be written (TBD)", warning)

    def test_needs_a_description(self):
        (error,) = check(rvt("(TBD)"))[0]
        self.assertIn('(TBD "what the step will do")', error)


if __name__ == "__main__":
    unittest.main()
