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

from . import gitutil
from .examples import RVTS



class TestRunLocally(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.config = {"environments": {
            "sim": {"workdir": str(self.tmp / "sim")},
            "lms": {"workdir": str(self.tmp / "lms")},
        }}

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def outcomes(self, report_id):
        return {
            ((r.get("variation") or {}).get("name"), r["environment"]): r["outcome"]
            for r in store.list_runs(self.tmp / "reports", report_id)
        }

    def test_every_variation_by_default(self):
        report_id, _ = run_locally(RVTS, ["SFC/tc_sfc_001.rst"], self.tmp / "reports",
                                   Host.from_config(self.config))
        self.assertEqual(self.outcomes(report_id), {
            ("standard", "sim"): "pass",
            ("extended", "sim"): "pass",
        })

    def test_one_variation_in_every_hosted_environment(self):
        report_id, _ = run_locally(
            RVTS, ["DSKY/tc_dsky_002.rst", "SFC/tc_sfc_001.rst"], self.tmp / "reports",
            Host.from_config(self.config),
            variations={"SFC/tc_sfc_001.rst::extended"})
        self.assertEqual(self.outcomes(report_id), {
            (None, "sim"): "pass",
            (None, "lms"): "pass",
            ("extended", "sim"): "pass",
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
        code, out = self.cli("DSKY/tc_dsky_002.rst")
        self.assertEqual(code, 0, out)
        self.assertIn("pass     DSKY/tc_dsky_002.rst (sim)", out)

        code, out = self.cli("CFG/tc_cfg_002.rst", "--uut", "lm=LUM099")
        self.assertEqual(code, 1)
        self.assertIn("fail     CFG/tc_cfg_002.rst", out)

        code, out = self.cli("DSKY/tc_dsky_005.rst")
        self.assertEqual(code, 2)
        self.assertIn("must come before the first step", out)


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
            "workspace": self.branch, "requirement": "LGC-DSK-002",
            "configured": "1", "environment": "sim"})
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

    def test_a_borrowed_worker_takes_no_jobs_until_given_back(self):
        self.http.post("/runner/queue", data={
            "workspace": self.branch, "requirement": "LGC-DSK-002",
            "configured": "1", "environment": "sim"})
        host = Host.from_config({"environments": {"sim": {"workdir": str(self.tmp / "sim")}}})
        local = Worker(LocalServer(self.db, self.tmp / "reports", "local://test"), host)
        local.check_in(started=True)
        self.assertTrue(local.borrow())
        workers = self.http.get("/runner/workers", headers={"Accept": "application/json"})
        self.assertEqual([w["status"] for w in workers.get_json()], ["console"])
        self.assertEqual(local.work_until_idle(), [])
        local.give_back()
        self.assertEqual(local.work_until_idle(), ["pass"])

    def test_borrowing_waits_for_the_job_running(self):
        local = Worker(LocalServer(self.db, self.tmp / "reports", "local://test"), Host())
        with local.lock:  # as while a job runs
            self.assertFalse(local.borrow(timeout=0.1))
        self.assertTrue(local.borrow(timeout=0.1))


if __name__ == "__main__":
    unittest.main()


class TestCliReference(unittest.TestCase):
    def test_the_reference_shows_the_help_as_it_is(self):
        import textwrap
        from automationv3 import cli
        reference = (Path(__file__).resolve().parents[1] / "docs" / "reference" / "cli.rst")
        self.assertIn(textwrap.indent(cli.__doc__.strip("\n"), "   "), reference.read_text())


class TestPathsUseSlashes(unittest.TestCase):
    """Reports, closures and traces name files with "/" between folders,
    on Windows too"""

    def test_script_paths(self):
        from pathlib import PureWindowsPath
        from unittest import mock
        with mock.patch.object(cli, "Path", PureWindowsPath):  # relative paths, as Windows reads them
            self.assertEqual(cli.script_paths(Path("."), ["lm\\descent\\p63.rst", "lm/a.rst"]),
                             ["lm/descent/p63.rst", "lm/a.rst"])
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        self.assertEqual(cli.script_paths(root.resolve(), [str(root / "lm" / "a.rst")]), ["lm/a.rst"])

    def test_closure_keys(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        report_id = store.create_report(root)
        files = {"lm/core.rst": "", "lm/descent/p63.rst": "(Wait 1)"}
        run_id = store.create_run(root, report_id, "lm/descent/p63.rst", files)
        self.assertEqual(store.read_closure(root, report_id, run_id), files)
        self.assertEqual(store.read_closure_file(root, report_id, run_id, "lm/descent/p63.rst"),
                         "(Wait 1)")
