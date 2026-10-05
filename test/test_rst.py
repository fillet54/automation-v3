import os
import re
import unittest

from automationv3.framework.rst import write_html_parts

class TestWriteHtmlParts(unittest.TestCase):

    def test_one_part_per_statement_without_trailing_newlines(self):
        # A one-line paragraph must not swallow the separator that follows
        parts = write_html_parts(["Docs", "More docs", "Last"])
        self.assertEqual(len(parts), 3)
        self.assertIn("Docs", parts[0])
        self.assertIn("More docs", parts[1])
        self.assertIn("Last", parts[2])
