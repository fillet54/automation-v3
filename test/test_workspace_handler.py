
import os
import unittest
import sqlite3
from pathlib import Path
from flask import Flask, url_for

from automationv3.editor.views.workspace import workspace
from automationv3.editor.views.editor import editor
from automationv3.database import init_db


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

    def test_open_outside_workspace(self):
        response = self.client.post(url_for('workspace.open_document',
                                            id='master',
                                            path='../rvts/../../x'))
        self.assertEqual(response.status_code, 404)

    def test_open_document(self):
        response = self.client.post(url_for('workspace.open_document',
                                            id='master',
                                            path='BRA/tc_bra_00001.rvt'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('editor-content-update', response.headers['Hx-Trigger'])

    def test_editor_flow(self):
        # Page load creates the workspace and its editor
        response = self.client.get(url_for('workspace.index', id='master'))
        self.assertEqual(response.status_code, 200)
        editor_id = 1

        self.client.post(url_for('workspace.open_document', id='master',
                                 path='BRA/tc_bra_00001.rvt'))
        self.client.post(url_for('workspace.open_document', id='master',
                                 path='BRA/tc_bra_00002.rvt'))

        response = self.client.get(url_for('editor.tabs', id=editor_id))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'tc_bra_00001.rvt', response.data)
        self.assertIn(b'tc_bra_00002.rvt', response.data)

        # Last opened document is active
        response = self.client.get(url_for('editor.content', id=editor_id))
        self.assertEqual(response.status_code, 200)

        from automationv3.database import get_db
        from automationv3.editor.editor import get_editor
        ed = get_editor(get_db(), editor_id)
        doc1, doc2 = ed.documents
        self.assertEqual(ed.active_document, doc2)

        # Draft then view raw
        response = self.client.post(
            url_for('editor.update_content', id=editor_id, document_id=doc2.id,
                    action='save-draft'),
            data={'value': '(Wait 2)'})
        self.assertEqual(response.status_code, 200)
        self.client.post(url_for('editor.update_content', id=editor_id,
                                 document_id=doc2.id, action='view-raw'))
        response = self.client.get(url_for('editor.content', id=editor_id))
        self.assertIn(b'(Wait 2)', response.data)

        # Save writes the draft to disk
        self.client.post(url_for('editor.update_content', id=editor_id,
                                 document_id=doc2.id, action='save'))
        self.assertEqual(doc2.path.read_text(), '(Wait 2)')

        # Closing the active tab selects the remaining one
        response = self.client.post(url_for('editor.update_tabs', id=editor_id,
                                            document_id=doc2.id, action='close'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'tc_bra_00002.rvt', response.data)
        ed = get_editor(get_db(), editor_id)
        self.assertEqual(ed.documents, [doc1])
        self.assertEqual(ed.active_document, doc1)

    def test_unknown_editor_and_document(self):
        response = self.client.get(url_for('editor.tabs', id=99))
        self.assertEqual(response.status_code, 404)
        response = self.client.post(url_for('editor.update_content', id=1,
                                             document_id='nope', action='save'))
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
        self.app = Flask(__name__)
        self.app.register_blueprint(workspace, url_prefix='/workspace')
        self.app.register_blueprint(editor, url_prefix='/editor')
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
