"""Rendering a script's statements, including blocks that render themselves"""

import unittest

from automationv3.framework import rst
from automationv3.framework.block import BlockResult, BuildingBlock, find_block
from automationv3.framework.requirement import Requirement
from automationv3.framework.statements import get_statements
from automationv3.services.database import connect, init_db
from automationv3.services.requirements import models

SCRIPT = '''
"
=========
The Title
=========

Requirements
------------
1. :req:`R1`
"
(Wait 1)
(Unknown :x 1)
'''


class StartWithConfig(BuildingBlock):
    """A block that shows its configuration as a table"""

    def name(self):
        return "StartWithConfig"

    def execute(self, config):
        return BlockResult(True)

    def as_html(self, config):
        rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in config.items())
        return f'<table class="config">\n{rows}\n</table>'


class TestStatements(unittest.TestCase):
    def tearDown(self):
        rst.set_requirement_lookup(None)
        get_statements.cache_clear()

    def test_one_statement_per_form(self):
        statements = get_statements(SCRIPT)
        self.assertEqual(len(statements), 3)
        self.assertIn("The Title", statements[0].html)
        self.assertIn("<strong>Wait</strong> 1 seconds", statements[1].html)
        self.assertIn('class="code clojure', statements[2].html)  # no block: code

    def test_requirements_resolve_through_the_lookup(self):
        self.assertIn("[R1]", get_statements(SCRIPT)[0].html)
        get_statements.cache_clear()

        # A requirements store, without any web app
        conn = connect(":memory:")
        init_db(conn)
        models.insert(conn, [Requirement("R1", "The system shall start", "SYS")])
        rst.set_requirement_lookup(lambda id: models.find_by_id(conn, id))
        self.assertIn("shall [R1]", get_statements(SCRIPT)[0].html)

    def test_blocks_render_themselves(self):
        (statement,) = get_statements('(StartWithConfig {:mode :normal :trim 3})')
        self.assertIn('<table class="config">', statement.html)
        self.assertIn("<td>3</td>", statement.html)
        self.assertNotIn("code clojure", statement.html)

    def test_variations_render_as_a_table(self):
        (statement,) = get_statements(
            '(variations "mode level" ["low" [:low 1] "high" [:high (+ 1 2)]])')
        html = statement.html
        self.assertIn("Variations</caption>", html)
        for cell in ("mode", "level", "low", ":low", "high", ":high", "(+ 1 2)"):
            self.assertIn(cell, html)
        self.assertNotIn("code clojure", html)

    def test_precondition_renders_check_and_heal(self):
        (statement,) = get_statements(
            '(Precondition "Ready" (ready?) :heal (StartWithConfig {:mode :x}))')
        self.assertIn("<strong>Precondition:</strong> Ready", statement.html)
        self.assertIn("ready?", statement.html)
        self.assertIn('<table class="config">', statement.html)  # the heal's block

    def test_sample_start_demo_block(self):
        (statement,) = get_statements(
            "(StartDemo {:mode :emergency :readings {:brake-pressure 70}})")
        self.assertIn("Configuration</caption>", statement.html)
        self.assertIn("brake-pressure", statement.html)

    def test_blocks_defined_after_import_are_found(self):
        class Later(StartWithConfig):
            def name(self):
                return "Later"

        self.assertIsNotNone(find_block(["Later", {}]))


if __name__ == "__main__":
    unittest.main()
