"""Blocks limited to variations with `:variations:`"""

import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

from automationv3.framework import document
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


class TestRollUp(unittest.TestCase):
    SCRIPT = doc(
        rvt("(def margin 5) (def gain 1)", "definitions"),
        rvt("(def margin 20)", "definitions", variations="degraded"),
        rvt("(def gain 3)", "definitions", variations="nominal"),
        VARIATIONS,
        rvt("(Verify limit > 0)"),
    )

    def entries(self, variation=None):
        return group([statement_item(s) for s in get_statements(self.SCRIPT)],
                     variation)

    def test_all_variations_keep_each_block(self):
        kinds = [kind for kind, _ in self.entries()]
        self.assertEqual(kinds[:3], ["definitions", "scoped", "scoped"])

    def test_one_variation_rolls_up_to_the_last_definitions(self):
        for variation, expected in [("degraded", [("gain", "1"), ("margin", "20")]),
                                    ("nominal", [("margin", "5"), ("gain", "3")])]:
            (first, *rest) = self.entries(variation)
            self.assertEqual(first[0], "definitions")
            self.assertNotIn("definitions", [kind for kind, _ in rest])
            self.assertNotIn("scoped", [kind for kind, _ in rest])
            shown = [(item["defines"], item["html"]) for item in first[1]]
            self.assertEqual([name for name, _ in shown], [n for n, _ in expected])
            for (_, html), (_, value) in zip(shown, expected):
                self.assertIn(f'<span class="literal number integer">{value}</span>', html)


def variant(variations, *chunks):
    """An rvt-variant directive holding `chunks` (prose and rvt blocks)"""
    body = textwrap.indent(doc(*chunks), "   ")
    return f".. rvt-variant::\n   :variations: {variations}\n\n{body}"


VARIANT_SCRIPT = doc(
    VARIATIONS,
    "For every variation.",
    variant("degraded",
            "Degraded runs at a lower limit.",
            rvt("(Verify limit = 40)", title="Lower limit"),
            rvt("(Verify limit < 50)")),
    "After.",
)


class TestVariant(unittest.TestCase):
    def test_content_is_limited_to_its_variations(self):
        parts = document.parse(VARIANT_SCRIPT)
        scoped = [(p.prose, p.variations, p.title) for p in parts]
        self.assertEqual(scoped, [
            (False, None, None),                    # variations
            (True, None, None),
            (True, ["degraded"], None),             # the variant's prose
            (False, ["degraded"], "Lower limit"),
            (False, ["degraded"], None),
            (True, None, None),
        ])
        self.assertEqual([p.line for p in parts][2:5], [10, 12, 16])

    def test_runs_only_for_its_variations(self):
        _, recorder = run(VARIANT_SCRIPT, variation="degraded")
        self.assertEqual(len(recorder.steps()), 2)
        comments = [kw["text"] for kind, kw in recorder.events if kind == "comment"]
        self.assertIn("Degraded runs at a lower limit.", comments)

        outcome, recorder = run(VARIANT_SCRIPT, variation="nominal")
        self.assertEqual((outcome, recorder.steps()), ("pass", []))
        comments = [kw["text"] for kind, kw in recorder.events if kind == "comment"]
        self.assertNotIn("Degraded runs at a lower limit.", comments)

    def test_blocks_may_narrow_it(self):
        script = doc(VARIATIONS, variant("degraded, nominal",
                                         rvt("(Wait 0)", variations="nominal")))
        (part,) = [p for p in document.parse(script) if not p.prose][1:]
        self.assertEqual(part.variations, ["nominal"])

        outside = doc(VARIATIONS, variant("degraded",
                                          rvt("(Wait 0)", variations="nominal")))
        (error,) = errors(outside)
        self.assertIn("nominal is outside its rvt-variant (degraded)", error)

    def test_needs_variations(self):
        (error,) = errors(doc(VARIATIONS, ".. rvt-variant::\n\n   Text.\n"))
        self.assertIn("rvt-variant needs a :variations: option", error)

    def test_names_are_checked(self):
        script = doc(VARIATIONS, variant("typo", "Only prose."))
        self.assertEqual(errors(script), [
            "s.rst: no variation named typo (the script declares degraded, nominal)"])

    def test_a_script_with_rvt_blocks_only_in_variants(self):
        self.assertTrue(document.has_rvt(variant("a", rvt("(Wait 0)"))))

    def test_one_variation_leaves_it_out(self):
        items = [statement_item(s) for s in get_statements(VARIANT_SCRIPT)]
        all_kinds = [kind for kind, _ in group(items)]
        self.assertIn("scoped", all_kinds)
        (kind, scoped) = [e for e in group(items) if e[0] == "scoped"][0]
        self.assertEqual([k for k, _ in scoped["entries"]],
                         ["statement", "titled", "statement"])
