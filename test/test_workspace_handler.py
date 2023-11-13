
import os
import unittest
import sqlite3
from pathlib import Path
from flask import Flask, url_for

from automationv3.editor.views.workspace import workspace
from automationv3.editor.models import Workspace 


class TestWorkspaceHandler(unittest.TestCase):
    def test_workspace_filesystem_tree(self):
        # Master Workspace
        response = self.client.get(url_for('workspace.tree', workspace_id='master'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'BRA', response.data)
        self.assertNotIn(b'TEST', response.data)

        # Branch1
        response = self.client.get(url_for('workspace.tree', workspace_id='branch1'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'BRA', response.data)
        self.assertIn(b'TEST', response.data)
    
    def test_workspace_filesystem_tree_open_close(self):
        # Closed
        response = self.client.get(url_for('workspace.tree', workspace_id='master'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'BRA', response.data)
        self.assertNotIn(b'tc_bra_00001.rvt', response.data)

        # Toggle open
        response = self.client.post(url_for('workspace.tree',
                                            workspace_id='master',
                                            path='BRA'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'tc_bra_00001.rvt', response.data)

        # Stays open
        response = self.client.get(url_for('workspace.tree', workspace_id='master'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'BRA', response.data)
        self.assertIn(b'tc_bra_00001.rvt', response.data)
    


    #################
    # Fixture Setup #
    #################

    def setUp(self):
        from .data import make_workspaces as gitutil
        import tempfile, shutil

        # Create and setup DB
        self.db_file = "test_treeview.db"
        self.conn = sqlite3.connect(self.db_file)
        Workspace.ensure_db(self.conn)


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
        self.app = Flask(__name__)
        self.app.register_blueprint(workspace, url_prefix='/workspace')
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
