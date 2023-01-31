import os
import unittest

from automationv2.server import app
from automationv2.repository import Requirement, RequirementsRepository

class TestRequirementHandler(unittest.TestCase):
    def setUp(self):

        # Sample DB
        self.db_file = "test_requirements.db"
        self.repo = RequirementsRepository(self.db_file)
        requirement1 = Requirement("R1", "Test requirement 1", "Test subsystem 1")
        requirement2 = Requirement("R2", "Test requirement 2", "Test subsystem 2")
        self.repo.add(requirement1)
        self.repo.add(requirement2)

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
        response = self.client.get('/requirements?subsystem=Test subsystem 2')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Test requirement 2', response.data)

    def test_index_list_subsystems(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Test subsystem 1', response.data)
        self.assertIn(b'Test subsystem 2', response.data)

    def test_requirements_by_subsystem_as_hxrequest(self):
        response = self.client.get('/requirements?subsystem=Test subsystem 2',
                                   headers={'HX-Request': 'true'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'Test subsystem 1', response.data)
        self.assertNotIn(b'Test subsystem 2', response.data)

if __name__ == '__main__':
    unittest.main()
