import unittest

from automationv3.services import jobs as models
from automationv3.services.requirements import models as requirement_models
from automationv3.services.worker import Host, Worker
from automationv3.services.worker.local import LocalServer
from automationv3.framework.requirement import Requirement

from .central import SCRIPTS, Central, link_path, sent_links
from .rvt import doc, rvt


class TestClientApi(unittest.TestCase):
    def setUp(self):
        self.server = Central(scripts=SCRIPTS)
        self.secret = self.server.token("user", "laptop", "ann@example.com")
        self.http = self.server.client()
        self.auth = {"Authorization": f"Bearer {self.secret}"}

    def tearDown(self):
        self.server.close()

    def get(self, path, **kw):
        return self.http.get(path, headers=self.auth, **kw)

    def post(self, path, json):
        return self.http.post(path, json=json, headers=self.auth)

    def test_signing_a_device_in(self):
        with sent_links() as sent:
            started = self.http.post("/api/login/start", json={
                "email": "bob@example.com", "device": "bob-laptop"}).get_json()
        ((to, link, device),) = sent
        self.assertEqual((to, device), ("bob@example.com", "bob-laptop"))
        poll = lambda: self.http.post("/api/login/poll", json={"code": started["code"]})
        self.assertEqual(poll().status_code, 202)

        browser = self.server.client()
        self.assertIn("Approve bob-laptop", browser.get(link_path(link)).get_data(True))
        self.assertIn("bob-laptop is signed in", browser.post(link_path(link)).get_data(True))
        got = poll().get_json()
        self.assertEqual(got["email"], "bob@example.com")
        me = self.http.get("/api/whoami",
                           headers={"Authorization": f"Bearer {got['token']}"}).get_json()
        self.assertEqual((me["email"], me["admin"], me["central"]),
                         ("bob@example.com", False, True))
        self.assertEqual(poll().status_code, 410)  # handed out once

    def test_login_start_turns_away_other_domains(self):
        with sent_links() as sent:
            response = self.http.post("/api/login/start", json={"email": "eve@evil.org"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(sent, [])

    def test_the_api_needs_a_token(self):
        self.assertEqual(self.http.get("/api/whoami").status_code, 401)
        self.assertEqual(self.http.get("/api/uuts").status_code, 401)

    def test_requirements_uuts_and_environments(self):
        with self.server.conn() as conn:
            requirement_models.insert(conn, [Requirement("R1", "The brake shall hold.")])
        found = self.get("/api/requirements?id=R1&id=NOPE").get_json()["requirements"]
        self.assertEqual(found["R1"]["text"], "The brake shall hold.")
        self.assertIsNone(found["NOPE"])
        uuts = self.get("/api/uuts").get_json()
        self.assertIn("1.0.0", [v["id"] for v in uuts["demo"]])
        self.assertEqual(self.get("/api/environments").get_json(), {})

    def test_scratch_uploads_run_as_the_user(self):
        files = {"plain/core.rst": SCRIPTS["plain/core.rst"],
                 "plain/mine.rst": doc("Not committed anywhere", rvt("(Wait 1) (Verify 1 = 1)"))}
        response = self.post("/api/scratch", {"workspace": "feature", "files": files,
                                              "scripts": ["plain/mine.rst"],
                                              "device": "laptop"})
        self.assertEqual(response.status_code, 201, response.get_data(True))
        (run,) = response.get_json()["runs"]
        self.assertEqual(run["status"], "pending")
        self.assertTrue(run["url"].endswith(f"/reports/scratch/runs/{run['id']}"))

        stored = models.scratch_runs(self.server.reports)[0]
        self.assertEqual((stored["source"], stored["queued_by"], stored["device"],
                          stored["workspace"]),
                         ("uploaded", "ann@example.com", "laptop", "feature"))

        worker = Worker(LocalServer(self.server.db, self.server.reports, "local://w"), Host())
        worker.check_in(started=True)
        self.assertEqual(worker.work_once(), "pass")
        status = self.get(f"/api/scratch/{run['id']}").get_json()
        self.assertEqual(status["outcome"], "pass")
        events = self.get(f"/api/scratch/{run['id']}/events?after=1").get_json()
        self.assertTrue(events["finished"])
        self.assertEqual(events["events"][-1]["kind"], "procedure_end")

    def test_uploads_are_checked(self):
        cases = [
            ({"files": {"../evil.rst": "x"}, "scripts": ["../evil.rst"]}, 400),
            ({"files": {"/etc/x.rst": "x"}, "scripts": ["/etc/x.rst"]}, 400),
            ({"files": {"a.rst": "x"}, "scripts": ["b.rst"]}, 400),
            ({"files": {}, "scripts": []}, 400),
        ]
        for data, status in cases:
            with self.subTest(data=data):
                self.assertEqual(self.post("/api/scratch", data).status_code, status)
        broken = self.post("/api/scratch", {"files": {"x.rst": rvt("(Nope 1)")},
                                            "scripts": ["x.rst"]})
        self.assertEqual(broken.status_code, 400)
        self.assertTrue(broken.get_json()["errors"])
