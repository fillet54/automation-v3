import unittest
from pathlib import Path

from automationv3.framework.testcase import EdnTestCase
from automationv3.database import db
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

        Requirement.metadata.create_all(db.engine)

        # Sample DB Data
        self.req1 = Requirement(id="R1", text="Test requirement 1", subsystem="Test-subsystem-1")
        self.req2 = Requirement(id="R2", text="Test requirement 2", subsystem="Test-subsystem-2")

        with db.session() as session:
                session.add_all([self.req1, self.req2])
                session.commit()

    def tearDown(self):
        Path(db.get_connection_str()).unlink()


    def test_title(self):
        tc = EdnTestCase('id1', edn_text)
        self.assertEqual('The Title', tc.title)

    def test_requirements(self):
        tc = EdnTestCase('id1', edn_text)
        req1 = Requirement(id="R1", text="Test requirement 1", subsystem="Test-subsystem-1")
        req2 = Requirement(id="R2", text="Test requirement 2", subsystem="Test-subsystem-2")
        self.assertEqual(set([req1, req2]), tc.requirements)

    def test_getstatements(self):
        tc = EdnTestCase('id1', edn_text)
        self.assertEqual(4, len(tc.statements))

