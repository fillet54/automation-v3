import os
import unittest
from pathlib import Path

from automationv3.services.database import connect, init_db
from automationv3.web.app import create_app
from automationv3.services.requirements import models
from automationv3.framework.requirement import Requirement

class TestRequirementHandler(unittest.TestCase):
    def setUp(self):

        self.db_file = "test_requirements.db"
        with connect(self.db_file) as conn:
            init_db(conn)

            # Sample DB Data
            models.insert(conn, [
                Requirement("R1", "Test requirement 1", "Test-subsystem-1"),
                Requirement("R2", "Test requirement 2", "Test-subsystem-2"),
            ])
        conn.close()

        # Setup a test app
        app = create_app(DB_PATH=self.db_file)
        app.testing = True
        self.client = app.test_client()

    def tearDown(self):
        os.remove(self.db_file)

    def test_requirements_handler(self):
        response = self.client.get('/requirements/R1')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Test requirement 1', response.data)

    def test_requirements_handler_missing(self):
        response = self.client.get('/requirements/R99')
        self.assertEqual(response.status_code, 404)

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
