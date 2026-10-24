import unittest

from automationv3.services.reports import store
from automationv3.services.worker import Host, Worker
from automationv3.services.worker.client import ServerClient

from .central import SCRIPTS, Central, HttpSession


class TestWorkerTokens(unittest.TestCase):
    def setUp(self):
        self.server = Central(scripts=SCRIPTS)
        self.ann = self.server.token("user", "laptop", "ann@example.com")
        self.http = self.server.client()

    def tearDown(self):
        self.server.close()

    def worker(self, token, url="http://w1"):
        session = HttpSession(self.server.app.test_client())
        return Worker(ServerClient("http://server", url, session=session, token=token),
                      Host.from_config({"environments": {"sim": {
                          "workdir": str(self.server.tmp / "sim")}}}))

    def queue(self, script):
        response = self.http.post("/runner/jobs", json={
            "workspace": self.server.branch, "script": script},
            headers={"Authorization": f"Bearer {self.ann}"})
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()

    def test_a_worker_needs_a_token(self):
        with self.assertRaisesRegex(PermissionError, "worker token"):
            self.worker(None).check_in(started=True)
        with self.assertRaises(PermissionError):
            self.worker(self.ann).check_in(started=True)  # a user's token won't do

    def test_a_worker_with_a_token_runs_jobs_and_runs_record_it(self):
        secret = self.server.token("worker", "bench-1", "lead@example.com")
        worker = self.worker(secret)
        self.assertTrue(worker.check_in(started=True))
        ids = self.queue("plain/pass.rst")
        self.assertEqual(worker.work_once(), "pass")
        run = store.load_run(self.server.reports, ids["report_id"], ids["run_id"])
        self.assertEqual(run["worker_token"], "bench-1")

        workers = self.server.client("lead@example.com").get("/runner/workers").get_data(True)
        self.assertIn("bench-1", workers)

    def test_a_worker_url_belongs_to_its_token(self):
        one = self.server.token("worker", "bench-1")
        two = self.server.token("worker", "bench-2")
        self.assertTrue(self.worker(one).check_in(started=True))
        with self.assertRaisesRegex(PermissionError, "another worker token"):
            self.worker(two).check_in()

    def test_revoked_tokens_stop_working(self):
        secret = self.server.token("worker", "bench-1")
        worker = self.worker(secret)
        worker.check_in(started=True)
        lead = self.server.client("lead@example.com")
        page = lead.get("/admin/").get_data(as_text=True)
        self.assertIn("bench-1", page)
        with self.server.conn() as conn:
            (token_id,) = conn.execute("SELECT id FROM api_tokens WHERE kind = 'worker'").fetchone()
        lead.post(f"/admin/workers/{token_id}/revoke")
        with self.assertRaises(PermissionError):
            worker.check_in()

    def test_admins_make_tokens_shown_once(self):
        lead = self.server.client("lead@example.com")
        page = lead.post("/admin/workers", data={"name": "bench-3"}).get_data(as_text=True)
        self.assertIn("av3w_", page)
        self.assertIn("isn't shown again", page)
        self.assertNotIn("av3w_", lead.get("/admin/").get_data(as_text=True))
        ann = self.server.client("ann@example.com")
        self.assertEqual(ann.post("/admin/workers", data={"name": "x"}).status_code, 403)
