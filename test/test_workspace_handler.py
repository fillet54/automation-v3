
from automationv3.vendor.paper_ui import flask as paper_ui_flask
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
        self.assertIn(b'GDN', response.data)
        self.assertNotIn(b'TEST', response.data)

        # Branch1
        response = self.client.get(url_for('workspace.tree', id='branch1'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'GDN', response.data)
        self.assertIn(b'TEST', response.data)
    
    def test_workspace_filesystem_tree_open_close(self):
        # Closed
        response = self.client.get(url_for('workspace.tree', id='master'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'GDN', response.data)
        self.assertNotIn(b'tc_gdn_001.rst', response.data)

        # Toggle open
        response = self.client.post(url_for('workspace.expand',
                                            id='master',
                                            path='GDN'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'tc_gdn_001.rst', response.data)

        # Stays open
        response = self.client.get(url_for('workspace.tree', id='master'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'GDN', response.data)
        self.assertIn(b'tc_gdn_001.rst', response.data)
    


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
        from . import gitutil
        import tempfile, shutil

        # Create and setup DB
        self.db_file = "test.db"
        self.conn = sqlite3.connect(self.db_file)
        init_db(self.conn)


        # Create workspaces
        from .examples import RVTS as rvtdir
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
        paper_ui_flask.init_app(self.app)  # the ui/ templates the pages import
        self.app.register_blueprint(workspace.bp, url_prefix='/workspace')
        self.app.config['DB_PATH'] = self.db_file
        self.app.config['WORKSPACE_PATH'] = self.gitdir / 'rvts'
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


class TestScriptsFolder(unittest.TestCase):
    """A workspace is a scripts folder anywhere in a git worktree; git
    finds the same folder in the other worktrees"""

    def setUp(self):
        import shutil
        import tempfile
        from automationv3.services.workspace import find_worktrees
        from . import gitutil
        from .gitutil import check_output_no_stderr
        self.find = find_worktrees
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        master = self.tmp / "master"
        (master / "tests" / "scripts").mkdir(parents=True)
        (master / "tests" / "scripts" / "a.rst").write_text("(Wait 1)")
        gitutil.create_repo(master)
        gitutil.create_worktree(master, self.tmp / "branch1")
        check_output_no_stderr(["git", "worktree", "add", "--detach",
                                str(self.tmp / "detached")], cwd=master)

    def test_a_folder_below_the_top(self):
        self.assertEqual(self.find(self.tmp / "branch1" / "tests" / "scripts"), {
            "master": self.tmp / "master" / "tests" / "scripts",
            "branch1": self.tmp / "branch1" / "tests" / "scripts",
        })

    def test_the_top_of_a_worktree(self):
        self.assertEqual(self.find(self.tmp / "master"),
                         {"master": self.tmp / "master", "branch1": self.tmp / "branch1"})

    def test_a_branch_without_the_folder_is_left_out(self):
        (self.tmp / "master" / "tests" / "more").mkdir()
        self.assertEqual(self.find(self.tmp / "master" / "tests" / "more"),
                         {"master": self.tmp / "master" / "tests" / "more"})
