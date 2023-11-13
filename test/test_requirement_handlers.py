import os
import unittest
import sqlite3
from pathlib import Path
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from automationv3 import editor 
from automationv3.requirements.views import requirements
from automationv3.requirements.models import Requirement

class TestRequirementHandler(unittest.TestCase):
    def setUp(self):
        
        self.db_file = "test_requirements.db"
        engine = create_engine(f"sqlite:///{self.db_file}")
        self.sessionmaker = sessionmaker(engine) 
        self.session = self.sessionmaker()

        Requirement.metadata.create_all(engine)

        # Sample DB Data
        req1 = Requirement(id="R1", text="Test requirement 1", subsystem="Test-subsystem-1")
        req2 = Requirement(id="R2", text="Test requirement 2", subsystem="Test-subsystem-2")
        self.session.add_all([req1, req2])
        self.session.commit()

        # Setup a test app
        app = Flask(__name__, template_folder=Path(editor.__file__).parent / 'templates')
        app.register_blueprint(requirements, url_prefix='/requirements')

        app.config['DB_PATH'] = self.db_file
        app.config['DB_SESSION_MAKER'] = self.sessionmaker
        app.testing = True
        self.client = app.test_client()

    def tearDown(self):
        self.session.close()
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
