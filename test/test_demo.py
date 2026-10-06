"""`automation-v3 demo`: a fresh demo folder, and the docs it serves"""

import json
import shutil
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from automationv3 import demo
from automationv3.services.database import connect
from automationv3.services.requirements import models as requirements
from automationv3.services.workspace import find_worktrees
from automationv3.web.app import create_app


def quiet(*args):
    pass


class TestDemoSetup(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / "demo"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_sets_up_a_workspace_with_branches(self):
        made = demo.setup(self.path, docs=False, log=quiet)
        worktrees = find_worktrees(made.workspace)
        self.assertEqual(sorted(worktrees), ["branch1", "branch2", "branch3", "master"])
        self.assertTrue((worktrees["master"] / "BRA" / "tc_bra_00004.rst").exists())

    def test_loads_the_sample_requirements(self):
        made = demo.setup(self.path, docs=False, log=quiet)
        with closing(connect(made.db_path)) as conn:
            found = requirements.find_by_id(conn, "VMCBRA00001")
        self.assertIsNotNone(found)

    def test_the_worker_works_inside_the_demo_folder(self):
        made = demo.setup(self.path, docs=False, log=quiet)
        config = json.loads(made.config.read_text())
        self.assertEqual(sorted(config["environments"]), ["bench", "sim"])
        for params in config["environments"].values():
            self.assertTrue(params["workdir"].startswith(str(self.path.resolve())))

    def test_running_again_replaces_the_earlier_demo(self):
        demo.setup(self.path, docs=False, log=quiet)
        (self.path / "leftover.txt").write_text("from before")
        demo.setup(self.path, docs=False, log=quiet)
        self.assertFalse((self.path / "leftover.txt").exists())

    def test_refuses_to_delete_a_folder_it_didnt_make(self):
        self.path.mkdir()
        (self.path / "important.txt").write_text("keep me")
        with self.assertRaises(demo.DemoError):
            demo.setup(self.path, docs=False, log=quiet)
        self.assertTrue((self.path / "important.txt").exists())

    def test_uses_an_empty_existing_folder(self):
        self.path.mkdir()
        demo.setup(self.path, docs=False, log=quiet)
        self.assertTrue((self.path / demo.MARKER).exists())


class TestDocsLink(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.made = demo.setup(self.tmp / "demo", docs=False, log=quiet)
        self.docs = self.tmp / "html"
        self.docs.mkdir()
        (self.docs / "index.html").write_text("<h1>The docs</h1>")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def client(self, docs_path):
        return create_app(DB_PATH=self.made.db_path, WORKSPACE_PATH=self.made.workspace,
                          REPORTS_PATH=self.made.reports, DOCS_PATH=docs_path,
                          TESTING=True).test_client()

    def test_serves_the_docs_with_a_link_in_the_nav(self):
        client = self.client(self.docs)
        with client.get("/docs/") as response:
            self.assertIn(b"The docs", response.data)
        page = client.get("/requirements/").get_data(as_text=True)
        self.assertIn('href="/docs/"', page)

    def test_no_docs_no_link(self):
        client = self.client(None)
        self.assertEqual(client.get("/docs/").status_code, 404)
        page = client.get("/requirements/").get_data(as_text=True)
        self.assertNotIn('href="/docs/"', page)
