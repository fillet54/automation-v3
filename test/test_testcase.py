import unittest
from pathlib import Path


from automationv3.framework.testcase import EdnTestCase
from automationv3.framework import rst
from automationv3.services.database import connect, init_db
from automationv3.services.requirements import models
from automationv3.framework.requirement import Requirement

edn_text = '''

"
=========
The Title
=========

Requirements
------------
1. :req:`R1`
2. :req:`R2`
"

"
Steps
-----
"
(Wait 1)

'''


class TestTestCase(unittest.TestCase):
    def setUp(self):
        # Requirement text comes from a plain sqlite store; no web app needed
        self.conn = connect(":memory:")
        init_db(self.conn)
        self.req1 = Requirement(id="R1", text="Test requirement 1", subsystem="Test-subsystem-1")
        self.req2 = Requirement(id="R2", text="Test requirement 2", subsystem="Test-subsystem-2")
        models.insert(self.conn, [self.req1, self.req2])
        rst.set_requirement_lookup(lambda id: models.find_by_id(self.conn, id))

    def tearDown(self):
        rst.set_requirement_lookup(None)
        self.conn.close()

    def test_title(self):
        tc = EdnTestCase('id1', edn_text)
        self.assertEqual('The Title', tc.title)

    def test_requirements(self):
        tc = EdnTestCase('id1', edn_text)
        req1 = Requirement(id="R1", text="Test requirement 1", subsystem="Test-subsystem-1")
        req2 = Requirement(id="R2", text="Test requirement 2", subsystem="Test-subsystem-2")
        self.assertEqual(set([req1, req2]), tc.requirements)

    def test_get_statements(self):
        tc = EdnTestCase('id1', edn_text)
        self.assertEqual(3, len(tc.statements))

    def test_update_statements(self):
        text = '''
"
-----
Title
-----
"

"
1. One
3. Three
"
'''
        tc = EdnTestCase('id1', text)
        tc.update_statement(1, '''

1. One
2. Two
3. Three
''')

        self.assertEqual(tc.text, '''\
"
-----
Title
-----
"

"
1. One
2. Two
3. Three
"
''')
