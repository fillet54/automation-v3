"""Definitions in scripts: the definitions section, and definitions elsewhere"""

import shutil
import tempfile
import unittest
from pathlib import Path

from automationv3.framework.closure import resolve
from automationv3.framework.executor import execute_closure
from automationv3.framework.planning import build_plan
from automationv3.framework.statements import get_statements

SCRIPT = '''
"
Title
=====
"

"
.. rvt::
   :definitions:
"
(def target 70)
(defn high? [p] (> p 50))

(variations "level" ["at-target" [target] "low" [10]])

"
Steps
-----
"
(Verify level = target)
(def doubled (* 2 target))
(Verify doubled = 140)
'''


class Recorder:
    def __init__(self):
        self.events = []

    def __getattr__(self, name):
        return lambda **kw: self.events.append((name[3:], kw))

    def steps(self):
        return [kw for kind, kw in self.events if kind == "step_end"]


def run(script, variation=None):
    recorder = Recorder()
    outcome = execute_closure({"s.rvt": script}, ["s.rvt"], recorder,
                              variation=variation)
    return outcome, recorder


class TestRunning(unittest.TestCase):
    def test_section_loads_before_variations_and_steps(self):
        outcome, recorder = run(SCRIPT, variation="at-target")
        self.assertEqual(outcome, "pass")
        self.assertEqual(run(SCRIPT, variation="low")[0], "fail")

    def test_definitions_are_not_reported_as_steps(self):
        _, recorder = run(SCRIPT, variation="at-target")
        self.assertEqual([s["stdout"] for s in recorder.steps()],
                         ["70 = 70", "140 = 140"])

    def test_a_failing_definition_fails_the_script(self):
        outcome, recorder = run("(def broken (missing-fn 1)) (Wait 1)")
        self.assertEqual(outcome, "fail")
        (step,) = recorder.steps()
        self.assertTrue(step["definition"])
        self.assertIn("missing-fn not found", step["stderr"])

    def test_server_side_planning_sees_the_section(self):
        root = Path(tempfile.mkdtemp())
        try:
            (root / "s.rvt").write_text(SCRIPT)
            plan = build_plan("w", root, ["s.rvt"])
            values = [v.values for v in plan.scripts[0].variations]
            self.assertEqual(values, [{"level": "70"}, {"level": "10"}])
        finally:
            shutil.rmtree(root)


class TestLint(unittest.TestCase):
    def errors(self, script):
        root = Path(tempfile.mkdtemp())
        try:
            (root / "s.rvt").write_text(script)
            return resolve(root, "s.rvt").errors
        finally:
            shutil.rmtree(root)

    def test_section_comes_first(self):
        self.assertEqual(self.errors(SCRIPT), [])
        late = '(Wait 1) "\n.. rvt::\n   :definitions:\n" (def a 1)'
        self.assertEqual(self.errors(late), [
            "s.rvt: the definitions section must come before any step or Precondition"])

    def test_unknown_options(self):
        self.assertEqual(self.errors('"\n.. rvt::\n   :defs:\n" (def a 1)'),
                         ["s.rvt: unknown rvt option :defs:"])


class TestRendering(unittest.TestCase):
    def test_statements_know_their_section(self):
        statements = get_statements(SCRIPT)
        marked = [(s.in_definitions, s.definition, s.defines) for s in statements]
        self.assertEqual(marked, [
            (False, False, None),       # title
            (True, False, None),        # the rvt directive
            (True, True, "target"),
            (True, True, "high?"),
            (False, False, None),       # variations
            (False, False, None),       # Steps heading
            (False, False, None),
            (False, True, "doubled"),   # a definition elsewhere
            (False, False, None),
        ])
        self.assertEqual(statements[1].html.strip(), "")


if __name__ == "__main__":
    unittest.main()
