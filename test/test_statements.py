"""Rendering a script's statements, including blocks that render themselves"""

import unittest

from automationv3.documents import core
from automationv3.framework import markup, rst
from automationv3.framework.block import BlockResult, BuildingBlock, find_block
from automationv3.framework.requirement import Requirement
from automationv3.framework.statements import get_statements
from automationv3.services.database import connect, init_db
from automationv3.services.requirements import models

from .rvt import rvt

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
    return core.write(core.parse(text), "html5")["body"]


class TestStatements(unittest.TestCase):
    def tearDown(self):
        rst.set_requirement_lookup(None)
        get_statements.cache_clear()

    def test_one_statement_per_form(self):
        statements = get_statements(SCRIPT)
        self.assertEqual(len(statements), 3)
        self.assertIn("The Title", statements[0].rst)
        self.assertEqual("**Wait** 1 seconds", statements[1].rst)
        self.assertIn(".. code-block:: clojure", statements[2].rst)  # no block: code

    def test_requirements_resolve_through_the_lookup(self):
        self.assertIn("[R1]", document_html(get_statements(SCRIPT)[0].rst))
        get_statements.cache_clear()

        # A requirements store, without any web app
        conn = connect(":memory:")
        init_db(conn)
        models.insert(conn, [Requirement("R1", "The system shall start", "SYS")])
        rst.set_requirement_lookup(lambda id: models.find_by_id(conn, id))
        self.assertIn("shall [R1]", document_html(get_statements(SCRIPT)[0].rst))

    def test_blocks_render_themselves(self):
        (statement,) = get_statements(rvt('(StartWithConfig {:mode :normal :trim 3})'))
        self.assertIn(".. list-table:: Config", statement.rst)
        self.assertIn("``3``", statement.rst)
        self.assertNotIn("code-block", statement.rst)

    def test_variations_render_as_a_table(self):
        (statement,) = get_statements(rvt(
            '(variations "mode level" ["low" [:low 1] "high" [:high (+ 1 2)]])'))
        html = document_html(statement.rst)
        self.assertIn("Variations</caption>", html)
        for cell in ("mode", "level", "low", ":low", "high", ":high", "(+ 1 2)"):
            self.assertIn(cell, html)
        self.assertNotIn("code-block", statement.rst)

    def test_precondition_renders_check_and_heal_on_their_own(self):
        (statement,) = get_statements(rvt(
            '(Precondition "Ready" (ready?) :heal "Start <it>" '
            "(StartWithConfig {:mode :x}))"))
        p = statement.precondition
        self.assertEqual((p["name"], p["heal_name"]), ("Ready", "Start <it>"))
        self.assertIn("ready?", p["check_rst"])
        self.assertIn(".. list-table:: Config", p["heal_rst"])  # the heal's block
        self.assertIn("**Precondition:** Ready", statement.rst)

    def test_precondition_without_heal(self):
        (statement,) = get_statements(rvt('(Precondition "Ready" (ready?)) (Wait 1)'))[:1]
        self.assertIsNone(statement.precondition["heal_rst"])
        self.assertIsNone(statement.precondition["heal_name"])

    def test_other_statements_are_not_preconditions(self):
        statements = get_statements(rvt('(Wait 1) (Precondition "R" (r?) :heal (h)) (Wait 2)'))
        self.assertEqual([s.precondition is not None for s in statements],
                         [False, True, False])
        self.assertIn("Wait", statements[2].rst)

    def test_sample_start_demo_block(self):
        (statement,) = get_statements(rvt(
            "(StartDemo {:mode :emergency :readings {:brake-pressure 70}})"))
        self.assertIn(".. list-table:: Configuration", statement.rst)
        self.assertIn("brake-pressure", statement.rst)

    def test_blocks_defined_after_import_are_found(self):
        class Later(StartWithConfig):
            def name(self):
                return "Later"

        self.assertIsNotNone(find_block(["Later", {}]))


if __name__ == "__main__":
    unittest.main()
