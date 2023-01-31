import unittest
import os

from automationv2.repository import RequirementsRepository, Requirement

class TestRequirementsRepository(unittest.TestCase):
    def setUp(self):
        self.db_file = "test_requirements.db"
        self.repo = RequirementsRepository(self.db_file)

    def tearDown(self):
        self.repo._conn.close()
        os.remove(self.db_file)

    def test_add_and_get(self):
        requirement = Requirement("R1", "Test requirement", "Test subsystem")
        self.repo.add(requirement)
        result = self.repo.get_by_id("R1")
        self.assertEqual(requirement.requirement_id, result.requirement_id)
        self.assertEqual(requirement.text, result.text)
        self.assertEqual(requirement.subsystem, result.subsystem)

    def test_get_all(self):
        requirement1 = Requirement("R1", "Test requirement 1", "Test subsystem 1")
        requirement2 = Requirement("R2", "Test requirement 2", "Test subsystem 2")
        self.repo.add(requirement1)
        self.repo.add(requirement2)
        results = self.repo.get_all()
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].requirement_id, "R1")
        self.assertEqual(results[1].requirement_id, "R2")
    
    def test_get_by_subsystem(self):
        requirement1 = Requirement("R1", "Test requirement 1", "Test subsystem 1")
        requirement2 = Requirement("R2", "Test requirement 2", "Test subsystem 2")
        self.repo.add(requirement1)
        self.repo.add(requirement2)
        results = self.repo.get_by_subsystem("Test subsystem 2")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].requirement_id, "R2")

    def test_get_subsystem(self):
        requirement1 = Requirement("R1", "Test requirement 1", "Test subsystem 1")
        requirement2 = Requirement("R2", "Test requirement 2", "Test subsystem 2")
        self.repo.add(requirement1)
        self.repo.add(requirement2)
        results = self.repo.get_subsystems()
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], "Test subsystem 1")
        self.assertEqual(results[1], "Test subsystem 2")

    def test_remove(self):
        requirement = Requirement("R1", "Test requirement", "Test subsystem")
        self.repo.add(requirement)
        self.repo.remove("R1")
        result = self.repo.get_by_id("R1")
        self.assertIsNone(result)



if __name__ == "__main__":
    unittest.main()
