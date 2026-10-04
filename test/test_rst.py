import os
import re
import unittest

from automationv3.framework.rst import split_rst_by_directives

class TestRstReader(unittest.TestCase):

    def test_split_no_directives(self):
        src = '''\
=====
TITLE
=====
Content
'''
        parts = split_rst_by_directives(src)

        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0], src)


    def test_split_single_directive(self):
        src = '''\
=====
TITLE
=====
Content

.. testcase::

    body
    one
    two

'''

        parts = split_rst_by_directives(src)

        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0], '''\
=====
TITLE
=====
Content
''')
        self.assertEqual(parts[1], '''\
.. testcase::

    body
    one
    two

''')
        




class TestWriteHtmlParts(unittest.TestCase):

    def test_one_part_per_statement_without_trailing_newlines(self):
        # A one-line paragraph must not swallow the separator that follows
        from automationv3.framework.rst import write_html_parts
        parts = write_html_parts(["Docs", "More docs", "Last"])
        self.assertEqual(len(parts), 3)
        self.assertIn("Docs", parts[0])
        self.assertIn("More docs", parts[1])
        self.assertIn("Last", parts[2])
