import unittest
from pathlib import Path

from flask import Flask

from automationv3.framework.testcase import EdnTestCase
from automationv3.database import get_db, init_db, close_db
from automationv3.requirements import models
from automationv3.requirements.models import Requirement

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
        # In-memory DB lives as long as the app context
        app = Flask(__name__)
        app.config["DB_PATH"] = ":memory:"
        app.teardown_appcontext(close_db)
        self.app_context = app.app_context()
        self.app_context.push()

        # Sample DB Data
        self.req1 = Requirement(id="R1", text="Test requirement 1", subsystem="Test-subsystem-1")
        self.req2 = Requirement(id="R2", text="Test requirement 2", subsystem="Test-subsystem-2")

        init_db(get_db())
        models.insert(get_db(), [self.req1, self.req2])

    def tearDown(self):
        self.app_context.pop()


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
