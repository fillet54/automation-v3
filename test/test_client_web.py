import shutil
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from automationv3.framework.requirement import Requirement
from automationv3.services import client
from automationv3.services import jobs as models
from automationv3.services.database import connect, init_db
from automationv3.services.reports import store
from automationv3.services.requirements import models as requirement_models
from automationv3.services.workspace import find_worktrees
from automationv3.web.app import create_app

from .central import SCRIPTS, Central, HttpSession
from .data import make_workspaces as gitutil
from .rvt import doc, rvt


class TestLocalClient(unittest.TestCase):
    """automation-v3 client: this machine's worktrees, the central server's
    requirements and workers"""

    def setUp(self):
        self.central = Central(scripts=SCRIPTS)
        with self.central.conn() as conn:
            requirement_models.insert(conn, [Requirement("R1", "The brake shall hold.")])
        token = self.central.token("user", "laptop", "ann@example.com")
        self.remote = client.CentralClient(
            "http://server", token, session=HttpSession(self.central.app.test_client()))

        # Ann's own clone, with an edit nobody has seen
        self.tmp = Path(tempfile.mkdtemp())
        repo = self.tmp / "clone"
        for path, text in SCRIPTS.items():
            (repo / "rvts" / path).parent.mkdir(parents=True, exist_ok=True)
            (repo / "rvts" / path).write_text(text)
        gitutil.create_repo(repo)
        self.branch = next(iter(find_worktrees(repo)))
        (repo / "rvts/plain/pass.rst").write_text(
            doc("Edited :req:`R1`", rvt("(Wait 1) (Wait 3)")))
        with closing(connect(self.tmp / "client.db")) as conn:
            init_db(conn)
        (self.tmp / "reports").mkdir()
        self.app = create_app(DB_PATH=self.tmp / "client.db", WORKSPACE_PATH=repo,
                              REPORTS_PATH=self.tmp / "reports", CENTRAL=self.remote,
                              LOCAL_WORKER=True, TESTING=True)
        self.http = self.app.test_client()

    def tearDown(self):
        self.central.close()
        shutil.rmtree(self.tmp)

    def page(self, path):
        response = self.http.get(path)
        self.assertEqual(response.status_code, 200, path)
        return response.get_data(as_text=True)

    def test_team_pages_are_on_the_central_server(self):
        page = self.page(f"/workspace/{self.branch}")
        self.assertIn('href="http://server/reports/"', page)
        self.assertIn('href="http://server/requirements/"', page)
        self.assertIn('href="/scratch/"', page)

    def test_requirements_come_from_the_central_server(self):
        page = self.page(f"/workspace/{self.branch}/view?path=plain/pass.rst")
        self.assertIn("The brake <strong class=\"shall\">shall [R1]</strong> hold", page)
        self.assertIn("Queue on the central server", page)
        self.assertIn('action="http://server/runner/new"', page)

    def test_run_in_scratch_on_the_central_server(self):
        response = self.http.post("/scratch/run", data={
            "workspace": self.branch, "script": "plain/pass.rst", "where": "central"})
        self.assertEqual(response.status_code, 302)
        # The central server's own address for the run (here, its test client's)
        self.assertRegex(response.headers["Location"], r"^http://[^/]+/reports/scratch/runs/")
        (run,) = models.scratch_runs(self.central.reports)
        self.assertEqual((run["source"], run["queued_by"], run["workspace"]),
                         ("uploaded", "ann@example.com", self.branch))
        closure = store.read_closure(self.central.reports, models.SCRATCH, run["id"])
        self.assertIn("(Wait 3)", closure["plain/pass.rst"])  # the edit went
        self.assertEqual(models.scratch_runs(self.tmp / "reports"), [])

        # On the central server, Run again runs the same uploaded files
        store.update_run(self.central.reports, models.SCRATCH, run["id"], outcome="pass")
        again = self.central.client("ann@example.com").post(
            f"/scratch/runs/{run['id']}/again")
        self.assertEqual(again.status_code, 302)
        newest = models.scratch_runs(self.central.reports)[0]
        self.assertNotEqual(newest["id"], run["id"])
        self.assertIn("(Wait 3)", store.read_closure(
            self.central.reports, models.SCRATCH, newest["id"])["plain/pass.rst"])

    def test_run_in_scratch_on_this_machine_stays_here(self):
        response = self.http.post("/scratch/run", data={
            "workspace": self.branch, "script": "plain/pass.rst", "where": "local"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].startswith("/reports/scratch/runs/"))
        self.assertEqual(len(models.scratch_runs(self.tmp / "reports")), 1)
        self.assertEqual(models.scratch_runs(self.central.reports), [])
        page = self.page("/scratch/")
        self.assertIn("http://server/scratch/", page)

    def test_a_broken_script_is_reported_before_uploading(self):
        (Path(self.app.config["WORKSPACES"].root(self.branch)) / "plain/bad.rst").write_text(
            rvt("(Nope 1)"))
        response = self.http.post("/scratch/run", data={
            "workspace": self.branch, "script": "plain/bad.rst"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(models.scratch_runs(self.central.reports), [])
