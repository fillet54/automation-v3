import unittest

from automationv3.framework.testcase import EdnTestCase

edn_text = '''

"
=========
The Title
=========

Requirements
------------
1. :req:`ABC123`
2. :req:`ABC456`
"

"
Steps
-----
"
(Wait 1)

'''


class TestTestCase(unittest.TestCase):

    def test_title(self):
        tc = EdnTestCase('id1', edn_text)
        self.assertEqual('The Title', tc.title)

    def test_requirements(self):
        tc = EdnTestCase('id1', edn_text)
        self.assertEqual(['ABC123', 'ABC456'], tc.requirements)


