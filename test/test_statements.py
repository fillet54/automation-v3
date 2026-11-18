"""Rendering a script's statements, including blocks that render themselves"""

import re
import unittest

from automationv3.documents import core
from automationv3.framework import markup, rst
from automationv3.framework.block import BlockResult, BuildingBlock, find_block
from automationv3.framework.requirement import Requirement
from automationv3.services.database import connect, init_db
from automationv3.services.requirements import models

from .rvt import doc, rvt, views

SCRIPT = '''
=========
The Title
=========

Requirements
------------
1. :req:`R1`

.. rvt::

   (Wait 1)
   (Unknown :x 1)
'''


class StartWithConfig(BuildingBlock):
    """A block that shows its configuration as a table"""

    def name(self):
        return "StartWithConfig"

    def execute(self, config):
        return BlockResult(True)

    def as_rst(self, config):
        return markup.mapping(config, caption="Config")


def document_html(text):
    """As a page renders: parsed (cached), then resolved"""
    return core.write(core.resolved(core.parse(text), core.Context()), "html5")["body"]


class TestStatements(unittest.TestCase):
    def tearDown(self):
        rst.set_requirement_lookup(None)

    def test_one_statement_per_form(self):
        from automationv3.documents import script
        statements = views(SCRIPT)
        self.assertEqual(len(statements), 2)  # prose isn't a statement
        self.assertEqual("**Wait** 1 seconds", statements[0].rst)
        self.assertIn(".. code-block:: clojure", statements[1].rst)  # no block: code
        self.assertIn("The Title", script.render(SCRIPT))  # the prose is the page's

    def test_requirements_resolve_through_the_lookup(self):
        from automationv3.documents import script
        self.assertIn("[R1]", document_html(script.render(SCRIPT)))

        # A requirements store, without any web app
        conn = connect(":memory:")
        init_db(conn)
        models.insert(conn, [Requirement("R1", "The system shall start", "SYS")])
        rst.set_requirement_lookup(lambda id: models.find_by_id(conn, id))
        self.assertIn("shall [R1]", document_html(script.render(SCRIPT)))

    def test_a_cached_page_shows_the_requirement_as_it_is_now(self):
        from automationv3.documents import script
        tree = script.parsed(SCRIPT)
        texts = {"R1": "The system shall start"}
        rst.set_requirement_lookup(lambda id: Requirement(id, texts[id], "SYS"))
        first = core.write(core.resolved(tree, core.Context()), "html5")["body"]
        texts["R1"] = "The system shall stop"
        self.assertIs(script.parsed(SCRIPT), tree)  # cached, by the text alone
        second = core.write(core.resolved(tree, core.Context()), "html5")["body"]
        self.assertIn("start", first)
        self.assertIn("stop", second)

    def test_blocks_render_themselves(self):
        (statement,) = views(rvt('(StartWithConfig {:mode :normal :trim 3})'))
        self.assertIn(".. list-table:: Config", statement.rst)
        self.assertIn("``3``", statement.rst)
        self.assertNotIn("code-block", statement.rst)

    def test_variations_render_as_a_table(self):
        (statement,) = views(rvt(
            '(variations "mode level" ["low" [:low 1] "high" [:high (+ 1 2)]])'))
        html = document_html(statement.rst)
        self.assertIn("Variations</caption>", html)
        for cell in ("mode", "level", "low", ":low", "high", ":high", "(+ 1 2)"):
            self.assertIn(cell, html)
        self.assertNotIn("code-block", statement.rst)

    def test_precondition_renders_check_and_heal_on_their_own(self):
        (statement,) = views(rvt(
            '(Precondition "Ready" (ready?) :heal "Start <it>" '
            "(StartWithConfig {:mode :x}))"))
        p = statement.precondition
        self.assertEqual((p["name"], p["heal_name"]), ("Ready", "Start <it>"))
        self.assertIn("ready?", p["check_rst"])
        self.assertIn(".. list-table:: Config", p["heal_rst"])  # the heal's block
        self.assertIn("**Precondition:** Ready", statement.rst)

    def test_precondition_without_heal(self):
        (statement,) = views(rvt('(Precondition "Ready" (ready?)) (Wait 1)'))[:1]
        self.assertIsNone(statement.precondition["heal_rst"])
        self.assertIsNone(statement.precondition["heal_name"])

    def test_other_statements_are_not_preconditions(self):
        statements = views(rvt('(Wait 1) (Precondition "R" (r?) :heal (h)) (Wait 2)'))
        self.assertEqual([s.precondition is not None for s in statements],
                         [False, True, False])
        self.assertIn("Wait", statements[2].rst)

    def test_start_lm_shows_its_configuration(self):
        (statement,) = views(rvt(
            "(StartLM {:mission :extended :start :high-gate})"))
        self.assertIn(".. list-table:: Configuration", statement.rst)
        self.assertIn("high-gate", statement.rst)

    def test_blocks_defined_after_import_are_found(self):
        class Later(StartWithConfig):
            def name(self):
                return "Later"

        self.assertIsNotNone(find_block(["Later", {}]))


class Recorder:
    """Every event the executor sends, as the worker would store it"""

    def __init__(self):
        self.events = []

    def __getattr__(self, name):
        if name.startswith("on_"):
            return lambda **kw: self.events.append({"kind": name[3:], **kw})
        raise AttributeError(name)


class TestRunPage(unittest.TestCase):
    def test_results_sit_by_their_steps_with_prose_between(self):
        from types import SimpleNamespace

        from automationv3.documents import script
        from automationv3.framework.closure import Closure
        from automationv3.framework import source
        from automationv3.framework.executor import execute_script
        from automationv3.framework.plugins import load_plugins

        load_plugins()
        text = doc("Title\n=====", "Before.", rvt("(Wait 0)"), "Between.",
                   rvt("(Verify 1 = 2)"))
        recorder = Recorder()
        self.assertEqual(execute_script(text, recorder), "fail")
        data = SimpleNamespace(
            events=lambda run: recorder.events,
            closure=lambda run: Closure("s.rst", files={"s.rst": text}, load_order=["s.rst"]),
            statements=lambda run: source.statements(source.parse(text)),
            links=SimpleNamespace(file=lambda *args: ""))
        run = {"id": "r1", "report_id": "x", "script": "s.rst", "outcome": "fail"}
        tree = script.parsed(text, None, results=True, variations=False)
        html = core.write(core.resolved(tree, core.Context(data=data, run=run)))["body"]
        words = " ".join(re.sub(r"<[^>]+>", " ", html).split())
        order = [words.index(t) for t in ("Before.", "Wait 0 seconds", "pass", "Between.",
                                          "Verify 1 = 2", "fail")]
        self.assertEqual(order, sorted(order))


if __name__ == "__main__":
    unittest.main()
