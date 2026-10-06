"""Blocks limited to variations with `:variations:`"""

import shutil
import tempfile
import unittest
from pathlib import Path

from automationv3.framework.closure import resolve
from automationv3.framework.planning import build_plan
from automationv3.framework.statements import get_statements
from automationv3.web.grouping import group, statement_item

from .rvt import doc, rvt
from .test_definitions import run

VARIATIONS = rvt('(variations "limit" ["nominal" [80] "degraded" [40]])')

SCRIPT = doc(
    rvt("(def margin 5)", "definitions"),
    rvt("(def margin 20)", "definitions", variations="degraded"),
    VARIATIONS,
    "Every variation checks the limit.",
    rvt("(Verify limit > 0)"),
    rvt("(Verify limit = 40) (Verify margin = 20)", variations="degraded"),
    rvt("(Verify limit = 80)", variations=" nominal "),
)


def with_root(files, action):
    root = Path(tempfile.mkdtemp())
    try:
        for path, text in files.items():
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(text)
        return action(root)
    finally:
        shutil.rmtree(root)


def errors(script, core=None):
    files = {"s.rst": script, **({"core.rst": core} if core else {})}
    return with_root(files, lambda root: resolve(root, "s.rst").errors)


class TestRunning(unittest.TestCase):
    def test_each_variation_runs_its_blocks(self):
        outcome, recorder = run(SCRIPT, variation="degraded")
        self.assertEqual(outcome, "pass")
        self.assertEqual([s["stdout"] for s in recorder.steps()],
                         ["40 > 0", "40 = 40", "20 = 20"])

        outcome, recorder = run(SCRIPT, variation="nominal")
        self.assertEqual(outcome, "pass")
        self.assertEqual([s["stdout"] for s in recorder.steps()],
                         ["80 > 0", "80 = 80"])

    def test_skipped_blocks_are_not_reported(self):
        _, recorder = run(SCRIPT, variation="nominal")
        indexes = [kw["index"] for kind, kw in recorder.events if kind == "step_start"]
        statements = get_statements(SCRIPT)
        self.assertTrue(all(statements[i].variations in (None, ["nominal"])
                            for i in indexes))

    def test_planning_sees_scoped_definitions(self):
        script = doc(
            rvt("(def base 1)", "definitions"),
            rvt("(def base 2)", "definitions", variations="b"),
            rvt('(variations "x" ["a" [base] "b" [base]])'),
        )
        plan = with_root({"s.rst": script},
                         lambda root: build_plan("w", root, ["s.rst"]))
        self.assertEqual([v.values for v in plan.scripts[0].variations],
                         [{"x": "1"}, {"x": "2"}])


class TestLint(unittest.TestCase):
    def test_a_valid_script(self):
        self.assertEqual(errors(SCRIPT), [])

    def test_unknown_names(self):
        script = doc(VARIATIONS, rvt("(Wait 1)", variations="nominal, typo"))
        self.assertEqual(errors(script), [
            "s.rst: no variation named typo (the script declares degraded, nominal)"])

    def test_no_variations_declared(self):
        self.assertEqual(errors(rvt("(Wait 1)", variations="nominal")), [
            "s.rst: a block is limited to variations, but the script declares none"])

    def test_declarations_cant_be_scoped(self):
        script = doc(VARIATIONS, rvt("(uut :demo)", variations="nominal"))
        self.assertEqual(errors(script), [
            "s.rst: uut can't be limited to variations"])

    def test_core_files_cant_scope(self):
        core = doc(VARIATIONS, rvt("(def a 1)", variations="nominal"))
        self.assertIn("core.rst: core.rst blocks can't be limited to variations",
                      errors(rvt("(Wait 1)"), core=core))

    def test_names_cant_hold_commas(self):
        script = rvt('(variations "x" ["a, b" [1]])')
        self.assertEqual(errors(script), [
            "s.rst: variation name a, b may not contain a comma"])

    def test_empty_option(self):
        (error,) = errors(doc(VARIATIONS, rvt("(Wait 1)", variations=",")))
        self.assertIn("expected variation names separated by commas", error)


class TestRendering(unittest.TestCase):
    def test_statements_know_their_variations(self):
        scoped = [s.variations for s in get_statements(SCRIPT)]
        self.assertEqual(scoped, [None, ["degraded"], None, None, None,
                                  ["degraded"], ["degraded"], ["nominal"]])

    def test_consecutive_scoped_statements_group_together(self):
        entries = group([statement_item(s) for s in get_statements(SCRIPT)])
        kinds = [(kind, entry["variations"] if kind == "scoped" else None)
                 for kind, entry in entries]
        self.assertEqual(kinds, [
            ("definitions", None),
            ("scoped", ["degraded"]),
            ("statement", None),     # variations
            ("statement", None),     # prose
            ("statement", None),
            ("scoped", ["degraded"]),
            ("scoped", ["nominal"]),
        ])
        self.assertEqual(len(entries[5][1]["entries"]), 2)
