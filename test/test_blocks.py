"""How BuildingBlocks receive a step's arguments"""

import unittest

from automationv3.framework import edn
from automationv3.framework.block import BlockResult, BuildingBlock, all_blocks
from automationv3.framework.executor import execute_closure

from .rvt import rvt

seen = {}


class Record(BuildingBlock):
    """Gets its arguments evaluated"""

    def execute(self, *args):
        seen["Record"] = args
        return BlockResult(True)


class RecordForms(BuildingBlock):
    """Gets its arguments exactly as written"""

    def execute_forms(self, *forms):
        seen["RecordForms"] = forms
        return BlockResult(True)


class RecordQuoted(BuildingBlock):
    """Gets `name` as written and the rest evaluated"""

    quoted = {"name"}

    def execute(self, value, name, *rest):
        seen["RecordQuoted"] = (value, name, rest)


class Recorder:
    def __init__(self):
        self.ends = []

    def __getattr__(self, name):
        if name == "on_step_end":
            return lambda **kw: self.ends.append(kw)
        return lambda **kw: None


def run(script, variation=None):
    files = {"core.rst": rvt("(def limit 80)"), "s.rst": rvt(script)}
    recorder = Recorder()
    outcome = execute_closure(files, ["core.rst", "s.rst"], recorder,
                              variation=variation)
    return outcome, recorder.ends


class TestBlockArguments(unittest.TestCase):
    def setUp(self):
        seen.clear()

    def test_execute_gets_evaluated_arguments(self):
        outcome, _ = run('(variations "mode" ["x" [:fast]]) '
                         "(Record limit (+ 1 2) {:mode mode :limit limit} [limit :k])",
                         variation="x")
        self.assertEqual(outcome, "pass")
        self.assertEqual(seen["Record"], (
            80, 3,
            {edn.Keyword("mode"): edn.Keyword("fast"), edn.Keyword("limit"): 80},
            [80, edn.Keyword("k")],
        ))

    def test_execute_forms_gets_arguments_as_written(self):
        outcome, _ = run("(RecordForms limit (+ 1 2) [a b])")
        self.assertEqual(outcome, "pass")
        limit, call, names = seen["RecordForms"]
        self.assertEqual((limit, type(limit)), (edn.Symbol("limit"), edn.Symbol))
        self.assertEqual(edn.writes(call).strip(), "(+ 1 2)")
        self.assertEqual(names, [edn.Symbol("a"), edn.Symbol("b")])

    def test_quoted_parameters_get_their_argument_as_written(self):
        outcome, _ = run("(RecordQuoted limit limit (+ limit 1))")
        self.assertEqual(outcome, "pass")  # an action returning nil passes
        value, name, rest = seen["RecordQuoted"]
        self.assertEqual((value, rest), (80, (81,)))
        self.assertEqual((name, type(name)), (edn.Symbol("limit"), edn.Symbol))

    def test_unknown_symbol_is_an_error(self):
        outcome, ends = run("(Record nope)")
        self.assertEqual(outcome, "error")
        self.assertIn("nope not found", ends[0]["stderr"])


if __name__ == "__main__":
    unittest.main()


class Documented(BuildingBlock):
    """Does a thing.

    Example::

        (Documented 1)
    """

    def execute(self, first, optional_arg=None, *rest):
        return BlockResult(True)


class Shaped(BuildingBlock):
    def usage(self):
        return "(Shaped {:key value})"

    def execute_forms(self, config):
        return BlockResult(True)


class TestBlockDocumentation(unittest.TestCase):
    def test_plain_returns_by_kind(self):
        class Check(BuildingBlock):
            kind = "assertion"
        class Act(BuildingBlock):
            pass
        self.assertEqual((Check().result(0).passed, Check().result(0).value), (False, False))
        self.assertEqual((Act().result(0).passed, Act().result(0).value), (True, 0))
        failed = Check().result(BlockResult(False, stdout="no"))
        self.assertEqual((failed.passed, failed.value, failed.stdout), (False, False, "no"))

    def test_usage_defaults_to_the_parameters_of_execute(self):
        self.assertEqual(Documented().usage(),
                         "(Documented first optional-arg? rest...)")

    def test_usage_uses_execute_forms_when_the_block_has_it(self):
        self.assertEqual(RecordForms().usage(), "(RecordForms forms...)")

    def test_a_block_can_write_its_own_usage(self):
        self.assertEqual(Shaped().usage(), "(Shaped {:key value})")

    def test_doc_is_the_class_docstring_dedented(self):
        self.assertEqual(Documented().doc(),
                         "Does a thing.\n\nExample::\n\n    (Documented 1)")

    def test_doc_is_empty_without_a_docstring_of_its_own(self):
        self.assertEqual(Shaped().doc(), "")

    def test_every_plugin_block_is_documented(self):
        for block in all_blocks():
            if type(block).__module__.startswith("automationv3.plugins."):
                with self.subTest(block=block.name()):
                    self.assertTrue(block.doc())
                    self.assertTrue(block.usage().startswith("(" + block.name()))
