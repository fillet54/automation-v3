import unittest

from automationv3.services import jobs as models
from automationv3.services.settings import Settings
from automationv3.services.worker import Host, Worker
from automationv3.services.worker.local import LocalServer

from .central import SCRIPTS, Central


class TestScratchFirst(unittest.TestCase):
    def setUp(self):
        self.server = Central(settings=Settings(), scripts=SCRIPTS)
        self.http = self.server.client()

    def tearDown(self):
        self.server.close()

    def test_scratch_runs_go_ahead_of_reports(self):
        self.http.post("/runner/jobs", json={"workspace": self.server.branch,
                                             "script": "plain/fail.rst"})
        self.http.post("/runner/jobs", json={"workspace": self.server.branch,
                                             "script": "plain/pass.rst"})
        self.http.post("/scratch/run", data={"workspace": self.server.branch,
                                             "script": "plain/pass.rst"})
        with self.server.conn() as conn:
            order = [(job.scratch, job.script) for job in models.find_jobs(conn, "pending")]
        self.assertEqual(order, [(True, "plain/pass.rst"), (False, "plain/fail.rst"),
                                 (False, "plain/pass.rst")])

        worker = Worker(LocalServer(self.server.db, self.server.reports, "local://w"),
                        Host())
        worker.check_in(started=True)
        self.assertEqual(worker.work_once(), "pass")
        self.assertEqual(models.scratch_runs(self.server.reports)[0]["outcome"], "pass")
