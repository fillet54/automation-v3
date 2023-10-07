import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session 
import os

from automationv3.requirements.models import Requirement

class TestRequirements(unittest.TestCase):
    def setUp(self):
        self.db_file = "test_requirements.db"
        engine = create_engine(f"sqlite:///{self.db_file}")
        self.session = Session(engine) 

        Requirement.metadata.create_all(engine)

        reqs = [
            Requirement(id="R1", text="Test requirement 1", subsystem="Test subsystem 1"),
            Requirement(id="R2", text="Test requirement 2", subsystem="Test subsystem 2"),
        ]
        self.session.add_all(reqs)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        os.remove(self.db_file)

    def test_add_and_get(self):
        self.session.add(Requirement(id="R3", text="Test requirement", subsystem="Test subsystem"))
        self.session.commit()
        result = self.session.query(Requirement).filter(Requirement.id == 'R3').one()
        self.assertEqual(result.id, "R3")
        self.assertEqual(result.text, "Test requirement")
        self.assertEqual(result.subsystem, "Test subsystem")

    def test_get_all(self):
        results = self.session.query(Requirement).all()
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].id, "R1")
        self.assertEqual(results[1].id, "R2")
    
    def test_get_by_subsystem(self):
        results = self.session.query(Requirement).filter(Requirement.subsystem == 'Test subsystem 2').all()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "R2")

    def test_get_subsystem(self):
        results = [r.subsystem 
                   for r in self.session.query(Requirement.subsystem).distinct()]
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], "Test subsystem 1")
        self.assertEqual(results[1], "Test subsystem 2")

    def test_delete(self):
        result = self.session.query(Requirement).filter(Requirement.id == 'R1').one()
        self.session.delete(result)
        self.session.commit()
        result = self.session.query(Requirement).filter(Requirement.id == 'R1').first()
        self.assertIsNone(result)

if __name__ == "__main__":
    unittest.main()
