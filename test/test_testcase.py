import unittest

from automationv3.framework.testcase import EdnTestCase

edn_text = '''

"
=========
The Title
=========
"

(Wait 1)

'''


class TestTestCase(unittest.TestCase):

    def test_title(self):
        tc = EdnTestCase('id1', edn_text)
        self.assertEqual('The Title', tc.title)


