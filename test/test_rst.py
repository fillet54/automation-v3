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
        


