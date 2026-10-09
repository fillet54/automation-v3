"""Composing blocks in scripts: how calls report and fail"""

import unittest

from automationv3.framework import context
from automationv3.framework.block import ACTION, ASSERTION, VALUE, BlockResult, BuildingBlock
from automationv3.framework.executor import execute_closure
from automationv3.framework.statements import get_statements

from .rvt import rvt

CORE = """
(def limit 80)

(defn check-pressure [p]
  (Verify p <= limit)
  (Wait 1)
  true)

(defn hard-stop [p]
  (step "Hard stop"
    (Wait 1)
    (Verify p <= limit)
    :stopped))

(defn via-defn [p]
  (hard-stop p))
"""


class Reading(BuildingBlock):
    """A value block for tests: gives back its argument doubled"""

    kind = VALUE

    def execute(self, x):
        return x * 2


class Broken(BuildingBlock):
    """An action that raises"""

    def execute(self):
        raise RuntimeError("the bench is unplugged")


class Refuses(BuildingBlock):
    """An action that fails without raising"""

    def execute(self):
        return BlockResult(False, stdout="refused")


class Recorder:
    def __init__(self):
        self.events = []

    def __getattr__(self, name):
        return lambda **kw: self.events.append((name[3:], kw))

    def of(self, kind):
        return [kw for k, kw in self.events if k == kind]

    def calls(self, index):
        return [c for c in self.of("call_end") if c["index"] == index]


def run(script, core=CORE):
    recorder = Recorder()
    files = {"core.rst": rvt(core) if core else "", "s.rst": rvt(script)}
    outcome = execute_closure(files, ["core.rst", "s.rst"], recorder)
    return outcome, recorder


class TestTopLevelAndDefn(unittest.TestCase):
    def test_block_statement_is_the_step(self):
        outcome, rec = run("(Verify 60 <= limit)")
        self.assertEqual(outcome, "pass")
        self.assertEqual(rec.of("step_end")[0]["stdout"], "60 <= 80")
        self.assertEqual(rec.of("call_end"), [])

    def test_blocks_in_a_defn_act_as_top_level(self):
        outcome, rec = run("(check-pressure 70)")
        self.assertEqual(outcome, "pass")
        calls = rec.calls(0)
        self.assertEqual([(c["call"], c["depth"], c["passed"]) for c in calls],
                         [(1, 0, True), (2, 0, True)])
        self.assertEqual(calls[0]["stdout"], "70 <= 80")
        self.assertEqual([c["block_kind"] for c in calls], [ASSERTION, ACTION])

    def test_failure_in_a_defn_stops_the_script(self):
        outcome, rec = run("(check-pressure 90) (Wait 99)")
        self.assertEqual(outcome, "fail")
        (step,) = rec.of("step_end")
        self.assertFalse(step["passed"])
        self.assertIn("(Verify p <= limit) failed", step["stderr"])
        # Wait 1 after the failing Verify never ran
        self.assertEqual(len(rec.calls(0)), 1)

    def test_only_blocks_fail_steps(self):
        for script in ["(- 10 10)", "false", "nil", "(if false 1)", "(= 1 2)"]:
            outcome, rec = run(script)
            self.assertEqual(outcome, "pass", script)

    def test_the_value_is_shown(self):
        _, rec = run("(+ 1 2)")
        self.assertEqual(rec.of("step_end")[0]["stdout"], "returned 3")

    def test_an_exception_is_an_error_not_a_failure(self):
        outcome, rec = run("(/ 1 0) (Wait 1)")
        self.assertEqual(outcome, "error")
        self.assertTrue(rec.of("step_end")[0]["error"])

    def test_a_block_that_raises_is_an_error(self):
        outcome, rec = run("(do (Broken))")
        self.assertEqual(outcome, "error")
        (call,) = rec.calls(0)
        self.assertTrue(call["error"])
        self.assertIn("the bench is unplugged", call["stderr"])
        self.assertEqual(run("(Broken)")[0], "error")

    def test_an_action_can_fail_without_raising(self):
        self.assertEqual(run("(Refuses)")[0], "fail")


class TestCallValues(unittest.TestCase):
    def test_a_value_block_gives_its_value(self):
        outcome, rec = run("(Verify (Reading 21) = 42)")
        self.assertEqual(outcome, "pass")
        (call,) = [c for c in rec.of("call_end") if c["block_kind"] == VALUE]
        self.assertEqual(call["value"], "42")

    def test_an_assertion_gives_true_or_false(self):
        outcome, rec = run("(Verify (= (try-ok? (Verify 1 = 2)) false))")
        self.assertEqual(outcome, "pass")

    def test_an_action_gives_what_it_returned(self):
        outcome, _ = run("(Verify (nil? (Wait 1)))")
        self.assertEqual(outcome, "pass")


class TestStepForm(unittest.TestCase):
    def test_calls_nest_under_the_step(self):
        outcome, rec = run("(hard-stop 75)")
        self.assertEqual(outcome, "pass")
        group, *inner = sorted(rec.calls(0), key=lambda c: c["call"])
        self.assertEqual((group["title"], group["depth"], group["parent"]),
                         ("Hard stop", 0, None))
        self.assertEqual({c["parent"] for c in inner}, {group["call"]})
        self.assertEqual({c["depth"] for c in inner}, {1})
        self.assertEqual(rec.of("step_end")[0]["stdout"], "returned :stopped")

    def test_a_failure_inside_stops_the_step_and_the_script(self):
        outcome, rec = run("(via-defn 95) (Wait 99)")
        self.assertEqual(outcome, "fail")
        group = [c for c in rec.calls(0) if c.get("title")][0]
        self.assertFalse(group["passed"])
        self.assertEqual(len(rec.of("step_end")), 1)

    def test_needs_a_title(self):
        self.assertEqual(run("(step (Wait 1))")[0], "error")


class TestTryAndQuietly(unittest.TestCase):
    def test_try_ok_branches_without_failing(self):
        outcome, rec = run("(if (try-ok? (Verify 1 = 2)) (Wait 5) (Wait 1))")
        self.assertEqual(outcome, "pass")
        check, wait = rec.calls(0)
        self.assertEqual((check["suppressed"], check["passed"]), (True, False))
        self.assertFalse(wait["suppressed"])
        self.assertEqual(rec.of("call_start")[1]["form"], "(Wait 1)")

    def test_try_ok_suppresses_a_failing_step_form(self):
        outcome, _ = run("(Verify (not (try-ok? (hard-stop 95))))")
        self.assertEqual(outcome, "pass")

    def test_try_gives_the_value_or_the_default(self):
        self.assertEqual(run("(Verify (try (Reading 2) 0) = 4)")[0], "pass")
        self.assertEqual(run("(Verify (try (Broken) :fallback) = :fallback)")[0], "pass")
        self.assertEqual(run("(Verify (try (do (Refuses) 1) 2) = 2)")[0], "pass")

    def test_try_does_not_hide_script_mistakes(self):
        self.assertEqual(run("(try-ok? (missing 1))")[0], "error")

    def test_quietly_marks_calls_but_failures_still_count(self):
        outcome, rec = run("(quietly (Wait 3))")
        self.assertEqual(outcome, "pass")
        self.assertTrue(rec.calls(0)[0]["quiet"])
        self.assertEqual(run("(quietly (Verify 1 = 2))")[0], "fail")


class TestRemovedForms(unittest.TestCase):
    def test_defblock_and_passes_say_what_replaced_them(self):
        outcome, rec = run("(defblock x [] 1)", core="")
        self.assertEqual(outcome, "error")
        self.assertIn("defblock was removed", rec.of("step_end")[0]["stderr"])
        outcome, rec = run("(passes? (Wait 1))", core="")
        self.assertIn("passes? was renamed try-ok?", rec.of("step_end")[0]["stderr"])


class TestVerify(unittest.TestCase):
    def test_operators(self):
        for script, outcome in [
            ("(Verify 1 = 1)", "pass"), ("(Verify 1 not= 1)", "fail"),
            ("(Verify 2 > 1)", "pass"), ("(Verify (+ 1 1) >= 3)", "fail"),
            ('(Verify "a" == "a")', "pass"), ("(Verify true)", "pass"),
            ("(Verify (< 2 1))", "fail"),
        ]:
            self.assertEqual(run(script)[0], outcome, script)

    def test_one_argument_shows_the_form_as_written(self):
        _, rec = run("(Verify (< 2 limit))")
        self.assertEqual(rec.of("step_end")[0]["stdout"], "(< 2 limit) is true")

    def test_renders_as_written(self):
        (statement,) = get_statements(rvt("(Verify (reading :x) <= max-pressure)"))
        self.assertIn("<strong>Verify</strong>", statement.html)
        self.assertIn("(reading :x) &lt;= max-pressure", statement.html)


class TestDefinitions(unittest.TestCase):
    def test_scripts_may_define_too(self):
        self.assertEqual(run("(defn ok [] (Verify 1 = 1)) (ok)", core="")[0], "pass")

    def test_definitions_shadow_blocks(self):
        outcome, rec = run("(Wait 1)", core="(defn Wait [n] (Verify false))")
        self.assertEqual(outcome, "fail")


if __name__ == "__main__":
    unittest.main()
