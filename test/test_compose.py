"""Composing blocks in scripts: how calls report and fail"""

import shutil
import tempfile
import unittest
from pathlib import Path

from automationv3.framework.closure import resolve
from automationv3.framework.executor import execute_closure
from automationv3.framework.statements import get_statements

from .rvt import rvt

CORE = """
(def limit 80)

(defn check-pressure [p]
  (Verify p <= limit)
  (Wait 1)
  true)

(defblock hard-stop [p]
  (Verify p > 1000)
  (if (Verify p <= limit) :stopped false))

(defblock always [result] result)

(defn via-defn [p]
  (hard-stop p))
"""


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

    def test_failure_in_a_defn_stops_the_script(self):
        outcome, rec = run("(check-pressure 90) (Wait 99)")
        self.assertEqual(outcome, "fail")
        (step,) = rec.of("step_end")
        self.assertFalse(step["passed"])
        self.assertIn("(Verify p <= limit) failed", step["stderr"])
        # Wait 1 after the failing Verify never ran
        self.assertEqual(len(rec.calls(0)), 1)

    def test_falsy_value_fails_the_step(self):
        outcome, _ = run("(always false)")
        self.assertEqual(outcome, "fail")


class TestDefblock(unittest.TestCase):
    def test_nested_calls_dont_stop_it(self):
        outcome, rec = run("(hard-stop 75)")
        self.assertEqual(outcome, "pass")
        calls = rec.calls(0)
        self.assertEqual([(c["depth"], c["passed"]) for c in calls],
                         [(1, False), (1, True)])
        self.assertEqual(rec.of("step_end")[0]["stdout"], "returned :stopped")

    def test_result_comes_from_the_returned_value(self):
        self.assertEqual(run("(hard-stop 95)")[0], "fail")  # if -> false
        self.assertEqual(run("(always :yes)")[0], "pass")

    def test_defblock_called_from_a_defn_is_one_call(self):
        outcome, rec = run("(via-defn 75)")
        self.assertEqual(outcome, "pass")
        outer, *inner = sorted(rec.calls(0), key=lambda c: c["call"])
        self.assertEqual(rec.of("call_start")[0]["form"], "(hard-stop 75)")
        self.assertEqual((outer["depth"], outer["parent"], outer["passed"]), (0, None, True))
        self.assertEqual({c["parent"] for c in inner}, {outer["call"]})
        self.assertEqual({c["depth"] for c in inner}, {1})

    def test_failing_defblock_in_a_defn_stops_it(self):
        outcome, _ = run("(via-defn 95) (Wait 99)")
        self.assertEqual(outcome, "fail")


class TestPassesAndQuietly(unittest.TestCase):
    def test_passes_branches_without_failing(self):
        outcome, rec = run("(if (passes? (Verify 1 = 2)) (Wait 5) (Wait 1))")
        self.assertEqual(outcome, "pass")
        check, wait = rec.calls(0)
        self.assertEqual((check["checked"], check["passed"]), (True, False))
        self.assertEqual(rec.of("call_start")[1]["form"], "(Wait 1)")

    def test_quietly_marks_calls_but_failures_still_count(self):
        outcome, rec = run("(quietly (Wait 3))")
        self.assertEqual(outcome, "pass")
        self.assertTrue(rec.calls(0)[0]["quiet"])
        self.assertEqual(run("(quietly (Verify 1 = 2))")[0], "fail")


class TestVerify(unittest.TestCase):
    def test_operators(self):
        for script, outcome in [
            ("(Verify 1 = 1)", "pass"), ("(Verify 1 not= 1)", "fail"),
            ("(Verify 2 > 1)", "pass"), ("(Verify (+ 1 1) >= 3)", "fail"),
            ('(Verify "a" == "a")', "pass"), ("(Verify true)", "pass"),
            ("(Verify (< 2 1))", "fail"),
        ]:
            self.assertEqual(run(script)[0], outcome, script)

    def test_renders_as_written(self):
        (statement,) = get_statements(rvt("(Verify (reading :x) <= max-pressure)"))
        self.assertIn("<strong>Verify</strong>", statement.html)
        self.assertIn("(reading :x) &lt;= max-pressure", statement.html)


class TestDefinitions(unittest.TestCase):
    def test_scripts_may_define_too(self):
        root = Path(tempfile.mkdtemp())
        try:
            (root / "s.rst").write_text(rvt("(defblock ok [] true) (ok)"))
            self.assertEqual(resolve(root, "s.rst").errors, [])
        finally:
            shutil.rmtree(root)
        self.assertEqual(run("(defblock ok [] (Verify 1 = 1)) (ok)", core="")[0], "pass")

    def test_definitions_shadow_blocks(self):
        outcome, rec = run("(Wait 1)", core="(defn Wait [n] false)")
        self.assertEqual(outcome, "fail")


if __name__ == "__main__":
    unittest.main()
