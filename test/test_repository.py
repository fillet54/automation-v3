import unittest

from automationv3.services.database import connect, init_db
from automationv3.services.requirements import models
from automationv3.framework.requirement import Requirement


class TestRequirements(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        init_db(self.conn)
        models.insert(self.conn, [
            Requirement("R1", "Test requirement 1", "Test subsystem 1"),
            Requirement("R2", "Test requirement 2", "Test subsystem 2"),
        ])

    def tearDown(self):
        self.conn.close()

    def test_add_and_get(self):
        models.insert(self.conn, [Requirement("R3", "Test requirement", "Test subsystem")])
        result = models.find_by_id(self.conn, "R3")
        self.assertEqual(result.id, "R3")
        self.assertEqual(result.text, "Test requirement")
        self.assertEqual(result.subsystem, "Test subsystem")

    def test_get_missing(self):
        self.assertIsNone(models.find_by_id(self.conn, "R99"))

    def test_get_all(self):
        results = models.find_all(self.conn)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].id, "R1")
        self.assertEqual(results[1].id, "R2")

    def test_get_by_subsystem(self):
        results = models.find_all(self.conn, "Test subsystem 2")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "R2")

    def test_get_subsystem(self):
        results = models.subsystems(self.conn)
        self.assertEqual(results, ["Test subsystem 1", "Test subsystem 2"])


if __name__ == "__main__":
    unittest.main()
