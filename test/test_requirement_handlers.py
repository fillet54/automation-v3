import os
import unittest
import sqlite3
from pathlib import Path
from flask import Flask

from automationv3.server.views.requirement_views import requirements
from automationv3.models import Requirements, Requirement

class TestRequirementHandler(unittest.TestCase):
    def setUp(self):

        # Sample DB
        self.db_file = Path("test_requirements.db").resolve()
        self.conn = sqlite3.connect(self.db_file)
        self.repo = Requirements(self.conn)
        requirement1 = Requirement("R1", "Test requirement 1", "Test-subsystem-1")
        requirement2 = Requirement("R2", "Test requirement 2", "Test-subsystem-2")
        self.repo.add(requirement1)
        self.repo.add(requirement2)

        # Setup a test app
        app = Flask(__name__)
        app.register_blueprint(requirements, url_prefix='/requirements')

        app.config['DB_PATH'] = self.db_file
        app.testing = True
        self.client = app.test_client()

    def tearDown(self):
        self.repo._conn.close()
        os.remove(self.db_file)

    def test_requirements_handler(self):
        response = self.client.get('/requirements/R1')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Test requirement 1', response.data)
    
    def test_requirements_by_subsystem_handler(self):
        response = self.client.get('/requirements/?subsystem=Test-subsystem-2')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Test requirement 2', response.data)

        # Test that subsystem is in the response too
        self.assertIn(b'Test-subsystem-1', response.data)
        self.assertIn(b'Test-subsystem-2', response.data)

    def test_requirements_by_subsystem_as_hxrequest(self):
        response = self.client.get('/requirements/?subsystem=Test-subsystem-2',
                                   headers={'HX-Request': 'true'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'Test subsystem 1', response.data)
        self.assertNotIn(b'Test subsystem 2', response.data)

if __name__ == '__main__':
    unittest.main()
