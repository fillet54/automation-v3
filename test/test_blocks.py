"""How BuildingBlocks receive a step's arguments"""

import unittest

from automationv3.framework import edn
from automationv3.framework.block import BlockResult, BuildingBlock
from automationv3.framework.executor import execute_closure

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


class Recorder:
    def __init__(self):
        self.ends = []

    def __getattr__(self, name):
        if name == "on_step_end":
            return lambda **kw: self.ends.append(kw)
        return lambda **kw: None


def run(script, variation=None):
    files = {"core.rvt": "(def limit 80)", "s.rvt": script}
    recorder = Recorder()
    outcome = execute_closure(files, ["core.rvt", "s.rvt"], recorder,
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

    def test_unknown_symbol_fails_the_step(self):
        outcome, ends = run("(Record nope)")
        self.assertEqual(outcome, "fail")
        self.assertIn("nope not found", ends[0]["stderr"])


if __name__ == "__main__":
    unittest.main()
