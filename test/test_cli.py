"""Running scripts locally, without a server, a database file or HTTP"""

import json
import shutil
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from automationv3 import cli
from automationv3.services.database import connect, init_db
from automationv3.services.reports import store
from automationv3.services.worker import Host, Worker
from automationv3.services.worker.local import LocalServer, run_locally
from automationv3.services.workspace import find_worktrees
from automationv3.web.app import create_app

from .data import make_workspaces as gitutil

RVTS = Path(__file__).resolve().parent / "data" / "rvts"


class TestRunLocally(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.config = {"environments": {
            "sim": {"workdir": str(self.tmp / "sim")},
            "bench": {"workdir": str(self.tmp / "bench")},
        }}

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def outcomes(self, report_id):
        return {
            ((r.get("variation") or {}).get("name"), r["environment"]): r["outcome"]
            for r in store.list_runs(self.tmp / "reports", report_id)
        }

    def test_every_variation_by_default(self):
        report_id, _ = run_locally(RVTS, ["BRA/tc_bra_00004.rvt"], self.tmp / "reports",
                                   Host.from_config(self.config))
        self.assertEqual(self.outcomes(report_id), {
            ("normal", "sim"): "pass",
            ("limp-home", "sim"): "pass",
            ("emergency", "sim"): "pass",
        })

    def test_one_variation_in_every_hosted_environment(self):
        report_id, _ = run_locally(
            RVTS, ["BRA/tc_bra_00005.rvt", "BRA/tc_bra_00004.rvt"], self.tmp / "reports",
            Host.from_config(self.config),
            variations={"BRA/tc_bra_00004.rvt::limp-home"})
        self.assertEqual(self.outcomes(report_id), {
            (None, "sim"): "pass",
            (None, "bench"): "pass",
            ("limp-home", "sim"): "pass",
        })

    def cli(self, *args):
        config = self.tmp / "worker.json"
        config.write_text(json.dumps(self.config))
        out = StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as exit:
            cli.main(["run", *args, "--root", str(RVTS), "--config", str(config),
                      "--reports-path", str(self.tmp / "reports")])
        return exit.exception.code, out.getvalue()

    def test_cli_exit_status(self):
        code, out = self.cli("BRA/tc_bra_00001.rvt")
        self.assertEqual(code, 0, out)
        self.assertIn("pass     BRA/tc_bra_00001.rvt (sim)", out)

        code, out = self.cli("BRA/tc_bra_00003.rvt", "--uut", "demo=1.0.0")
        self.assertEqual(code, 1)
        self.assertIn("fail     BRA/tc_bra_00003.rvt", out)

        code, out = self.cli("BRA/tc_bra_00007.rvt")
        self.assertEqual(code, 2)
        self.assertIn("belongs in a core.rvt", out)


class TestServerWithLocalWorker(unittest.TestCase):
    """The server's --local-worker: a worker in the server process"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        gitdir = self.tmp / "repo"
        shutil.copytree(RVTS, gitdir / "rvts")
        gitutil.create_repo(gitdir)
        self.branch = next(iter(find_worktrees(gitdir)))
        self.db = self.tmp / "test.db"
        with connect(self.db) as conn:
            init_db(conn)
        app = create_app(DB_PATH=self.db, REPORTS_PATH=self.tmp / "reports",
                         WORKSPACE_PATH=gitdir, TESTING=True)
        (self.tmp / "reports").mkdir()
        self.http = app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_jobs_queued_in_the_app_run_in_process(self):
        response = self.http.post("/runner/queue", data={
            "workspace": self.branch, "requirement": "VMCFUE00004"})
        report_id = response.headers["Location"].rstrip("/").split("/")[-1]

        # The worker's own thread, with its own connection to the same file
        host = Host.from_config({"environments": {"sim": {"workdir": str(self.tmp / "sim")}}})
        local = Worker(LocalServer(self.db, self.tmp / "reports", "local://test"), host)
        local.check_in(started=True)
        outcomes = []
        thread = threading.Thread(target=lambda: outcomes.extend(local.work_until_idle()))
        thread.start()
        thread.join(30)

        self.assertEqual(outcomes, ["pass"])
        page = self.http.get(f"/reports/{report_id}")
        self.assertIn(b">Green<", page.data)
        workers = self.http.get("/runner/workers", headers={"Accept": "application/json"})
        self.assertIn("local://test", [w["url"] for w in workers.get_json()])


if __name__ == "__main__":
    unittest.main()
