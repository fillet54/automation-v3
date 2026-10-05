
import os
import unittest
import sqlite3
from pathlib import Path
from flask import Flask, url_for

import automationv3
from automationv3.web import TEMPLATES
from automationv3.web import workspace
from automationv3.services.database import init_db


class TestWorkspaceHandler(unittest.TestCase):
    def test_workspace_filesystem_tree(self):
        # Master Workspace
        response = self.client.get(url_for('workspace.tree', id='master'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'BRA', response.data)
        self.assertNotIn(b'TEST', response.data)

        # Branch1
        response = self.client.get(url_for('workspace.tree', id='branch1'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'BRA', response.data)
        self.assertIn(b'TEST', response.data)
    
    def test_workspace_filesystem_tree_open_close(self):
        # Closed
        response = self.client.get(url_for('workspace.tree', id='master'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'BRA', response.data)
        self.assertNotIn(b'tc_bra_00001.rvt', response.data)

        # Toggle open
        response = self.client.post(url_for('workspace.expand',
                                            id='master',
                                            path='BRA'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'tc_bra_00001.rvt', response.data)

        # Stays open
        response = self.client.get(url_for('workspace.tree', id='master'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'BRA', response.data)
        self.assertIn(b'tc_bra_00001.rvt', response.data)
    


    def test_unknown_workspace(self):
        response = self.client.get(url_for('workspace.tree', id='nope'))
        self.assertEqual(response.status_code, 404)

    def test_expand_outside_workspace(self):
        response = self.client.post(url_for('workspace.expand',
                                            id='master',
                                            path='../../'))
        self.assertEqual(response.status_code, 404)

    #################
    # Fixture Setup #
    #################

    def setUp(self):
        from .data import make_workspaces as gitutil
        import tempfile, shutil

        # Create and setup DB
        self.db_file = "test.db"
        self.conn = sqlite3.connect(self.db_file)
        init_db(self.conn)


        # Create workspaces
        rvtdir = Path(__file__).resolve().parent / 'data' / 'rvts'
        self.tempdir = Path(tempfile.mkdtemp())
        self.gitdir = self.tempdir / 'master'
        shutil.copytree(rvtdir, self.gitdir / 'rvts')
        gitutil.create_repo(self.gitdir)
        
        # Create some worktrees
        worktrees = ['branch1', 'branch2', 'branch3']
        for worktree in worktrees:
            workdir = self.gitdir.parent / worktree
            gitutil.create_worktree(self.gitdir, workdir)

        # Make unique data in branch1
        (self.tempdir / 'branch1' / 'rvts' / 'TEST').mkdir()


        # Setup a test app
        templates = TEMPLATES
        self.app = Flask(__name__, template_folder=templates)
        self.app.register_blueprint(workspace.bp, url_prefix='/workspace')
        self.app.config['DB_PATH'] = self.db_file
        self.app.config['WORKSPACE_PATH'] = self.gitdir
        self.app.testing = True
        self.app_context = self.app.test_request_context()
        self.app_context.push()
        self.client = self.app.test_client()

    def tearDown(self):
        import shutil

        self.app_context.pop()
        self.conn.close()
        os.remove(self.db_file)

        shutil.rmtree(self.tempdir)


if __name__ == '__main__':
    unittest.main()
