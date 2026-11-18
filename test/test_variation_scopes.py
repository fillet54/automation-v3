"""Blocks limited to variations with `:variations:`"""

import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

from automationv3.framework import cards, source
from automationv3.framework.closure import resolve
from automationv3.framework.planning import build_plan
from automationv3.documents import script as pages

from .rvt import doc, page_entries, rvt
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
        forms = source.statements(source.parse(SCRIPT))
        self.assertTrue(all(forms[i].variations in (None, ["nominal"]) for i in indexes))

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
        script = doc(VARIATIONS, rvt("(uut :lm)", variations="nominal"))
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
        scoped = [s.variations for s in source.statements(source.parse(SCRIPT))]
        self.assertEqual(scoped, [None, ["degraded"], None, None,
                                  ["degraded"], ["degraded"], ["nominal"]])

    def test_each_scoped_block_is_its_own_entry(self):
        entries = page_entries(SCRIPT)
        self.assertEqual([(c, summary) for c, summary, _ in entries], [
            ("block definitions collapsible", "Definitions margin"),
            ("scoped", "Only for degraded"),
            ("block", ""),     # variations
            ("block", ""),
            ("scoped", "Only for degraded"),
            ("scoped", "Only for nominal"),
        ])
        (inner,) = entries[4][2]
        self.assertEqual(inner[0], "block")
        self.assertEqual(len(inner[2]), 2)  # its two steps


class TestRollUp(unittest.TestCase):
    SCRIPT = doc(
        rvt("(def margin 5) (def gain 1)", "definitions"),
        rvt("(def margin 20)", "definitions", variations="degraded"),
        rvt("(def gain 3)", "definitions", variations="nominal"),
        VARIATIONS,
        rvt("(Verify limit > 0)"),
    )

    def test_all_variations_keep_each_block(self):
        kinds = [(c, summary) for c, summary, _ in page_entries(self.SCRIPT)]
        self.assertEqual(kinds[:3], [("block definitions collapsible", "Definitions margin, gain"),
                                     ("scoped", "Only for degraded"),
                                     ("scoped", "Only for nominal")])

    def test_one_variation_rolls_up_to_the_last_definitions(self):
        for variation, expected in [("degraded", [("gain", "1"), ("margin", "20")]),
                                    ("nominal", [("margin", "5"), ("gain", "3")])]:
            (first, *rest) = page_entries(self.SCRIPT, variation=variation)
            names = ", ".join(n for n, _ in expected)
            self.assertEqual(first[:2], ("block definitions collapsible", f"Definitions {names}"))
            self.assertNotIn("scoped", [c for c, _, _ in rest])
            self.assertFalse(any("definitions" in c for c, _, _ in rest))
            written = pages.render(self.SCRIPT, variation=variation)
            for name, value in expected:
                self.assertIn(f"(def {name} {value})", written)


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
        forms = source.statements(source.parse(VARIANT_SCRIPT))
        self.assertEqual([(s.variations, s.title, s.line) for s in forms], [
            (None, None, 1),                         # variations
            (["degraded"], "Lower limit", 12),
            (["degraded"], None, 16),
        ])
        (variant,) = [c for c in cards.split(VARIANT_SCRIPT) if c.kind == cards.VARIANT]
        prose = variant.children[0]  # the variant's prose: its own card in it
        self.assertEqual((prose.kind, prose.text, prose.line),
                         (cards.PROSE, "Degraded runs at a lower limit.", 10))

    def test_runs_only_for_its_variations(self):
        _, recorder = run(VARIANT_SCRIPT, variation="degraded")
        self.assertEqual(len(recorder.steps()), 2)

        outcome, recorder = run(VARIANT_SCRIPT, variation="nominal")
        self.assertEqual((outcome, recorder.steps()), ("pass", []))
        # prose isn't reported, inside a variant or out
        self.assertNotIn("comment", [kind for kind, _ in recorder.events])

    def test_blocks_may_narrow_it(self):
        script = doc(VARIATIONS, variant("degraded, nominal",
                                         rvt("(Wait 0)", variations="nominal")))
        (part,) = source.statements(source.parse(script))[1:]
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
        self.assertTrue(source.has_rvt(variant("a", rvt("(Wait 0)"))))

    def test_one_variation_leaves_it_out(self):
        entries = page_entries(VARIANT_SCRIPT)
        (classes, summary, inner) = [e for e in entries if "variant" in e[0]][0]
        self.assertEqual((classes, summary), ("scoped variant", "Only for degraded"))
        self.assertEqual([(c, t) for c, t, _ in inner],
                         [("block titled collapsible", "Lower limit"), ("block", "")])
        self.assertIn("Degraded runs at a lower limit.", pages.render(VARIANT_SCRIPT))
        self.assertFalse([e for e in page_entries(VARIANT_SCRIPT, variation="nominal")
                          if "variant" in e[0]])
        self.assertNotIn("Degraded runs", pages.render(VARIANT_SCRIPT, variation="nominal"))