"""Definitions in scripts: the definitions section, and definitions elsewhere"""

import shutil
import tempfile
import unittest
from pathlib import Path

from automationv3.framework.closure import resolve
from automationv3.framework.executor import execute_closure
from automationv3.framework.planning import build_plan
from automationv3.framework.statements import get_statements

from .rvt import doc, rvt

SCRIPT = '''
Title
=====

.. rvt::
   :definitions:

   (def target 70)
   (defn high? [p] (> p 50))

.. rvt::

   (variations "level" ["at-target" [target] "low" [10]])

Steps
-----

.. rvt::

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
    outcome = execute_closure({"s.rst": script}, ["s.rst"], recorder,
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

    def test_a_failing_definition_ends_the_script_in_error(self):
        outcome, recorder = run(rvt("(def broken (missing-fn 1)) (Wait 1)"))
        self.assertEqual(outcome, "error")
        (step,) = recorder.steps()
        self.assertTrue(step["definition"])
        self.assertIn("missing-fn not found", step["stderr"])

    def test_server_side_planning_sees_the_section(self):
        root = Path(tempfile.mkdtemp())
        try:
            (root / "s.rst").write_text(SCRIPT)
            plan = build_plan("w", root, ["s.rst"])
            values = [v.values for v in plan.scripts[0].variations]
            self.assertEqual(values, [{"level": "70"}, {"level": "10"}])
        finally:
            shutil.rmtree(root)


class TestLint(unittest.TestCase):
    def errors(self, script):
        root = Path(tempfile.mkdtemp())
        try:
            (root / "s.rst").write_text(script)
            return resolve(root, "s.rst").errors
        finally:
            shutil.rmtree(root)

    def test_section_comes_first(self):
        self.assertEqual(self.errors(SCRIPT), [])
        late = doc(rvt("(Wait 1)"), rvt("(def a 1)", "definitions"))
        self.assertEqual(self.errors(late), [
            "s.rst: the definitions section must come before any step or Precondition"])
        mixed = rvt("(def a 1) (Wait 1)", "definitions")
        self.assertEqual(self.errors(mixed), [
            "s.rst: a :definitions: block may only hold definitions, not (Wait 1)"])

    def test_unknown_options(self):
        errors = self.errors(rvt("(def a 1)", "defs"))
        self.assertEqual(len(errors), 1)
        self.assertIn('unknown option: "defs"', errors[0])


class TestRendering(unittest.TestCase):
    def test_statements_know_their_section(self):
        statements = get_statements(SCRIPT)
        marked = [(s.in_definitions, s.definition, s.defines) for s in statements]
        self.assertEqual(marked, [
            (False, False, None),       # title
            (True, True, "target"),     # the definitions block
            (True, True, "high?"),
            (False, False, None),       # variations
            (False, False, None),       # Steps heading
            (False, False, None),
            (False, True, "doubled"),   # a definition elsewhere
            (False, False, None),
        ])


if __name__ == "__main__":
    unittest.main()
