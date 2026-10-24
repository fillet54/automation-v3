import unittest

from automationv3.services import jobs as models
from automationv3.services.reports import store
from automationv3.services.settings import Settings

from .central import SCRIPTS, Central


class TestOwnership(unittest.TestCase):
    def setUp(self):
        self.server = Central(scripts=SCRIPTS)
        self.ann = self.server.client("ann@example.com")
        self.bob = self.server.client("bob@example.com")
        self.lead = self.server.client("lead@example.com")

    def tearDown(self):
        self.server.close()

    def new_report(self, http, name):
        response = http.post("/reports/new", data={"name": name,
                                                   "workspace": self.server.branch})
        self.assertEqual(response.status_code, 302)
        return response.headers["Location"].rsplit("/", 1)[1]

    def queue_into(self, http, report_id):
        return http.post("/runner/queue", data={"report": report_id,
                                                "script": "plain/pass.rst"})

    def test_reports_are_owned_and_lists_show_mine(self):
        mine = self.new_report(self.ann, "Ann's")
        self.new_report(self.bob, "Bob's")
        report = store.load_report(self.server.reports, mine)
        self.assertEqual((report["owner"], report["collaborators"]), ("ann@example.com", []))

        page = self.ann.get("/reports/").get_data(as_text=True)
        self.assertIn("Ann&#39;s", page)
        self.assertNotIn("Bob&#39;s", page)
        everyone = self.ann.get("/reports/?who=everyone").get_data(as_text=True)
        self.assertIn("Bob&#39;s", everyone)
        self.assertIn("bob@example.com", everyone)

    def test_only_members_and_admins_change_a_report(self):
        report_id = self.new_report(self.ann, "Ann's")
        self.assertEqual(self.queue_into(self.bob, report_id).status_code, 403)
        self.assertEqual(self.bob.post(f"/reports/{report_id}/rename",
                                       data={"name": "Mine now"}).status_code, 403)
        self.assertEqual(self.bob.post(f"/reports/{report_id}/export").status_code, 403)
        # Bob can read it, and sees it is view only
        page = self.bob.get(f"/reports/{report_id}").get_data(as_text=True)
        self.assertIn("View only", page)

        self.assertEqual(self.queue_into(self.ann, report_id).status_code, 302)
        self.assertEqual(self.lead.post(f"/reports/{report_id}/rename",
                                        data={"name": "Renamed"}).status_code, 302)
        (run,) = store.list_runs(self.server.reports, report_id)
        self.assertEqual(run["queued_by"], "ann@example.com")

    def test_non_members_see_no_change_buttons(self):
        report_id = self.new_report(self.ann, "Ann's")
        self.assertEqual(self.queue_into(self.ann, report_id).status_code, 302)
        changes = [f"/reports/{report_id}/{action}"
                   for action in ("rename", "export", "document")]
        ann = self.ann.get(f"/reports/{report_id}").get_data(as_text=True)
        bob = self.bob.get(f"/reports/{report_id}").get_data(as_text=True)
        for url in changes:
            self.assertIn(url, ann)
            self.assertNotIn(url, bob)
        self.assertIn("Edit document…", ann)
        self.assertNotIn("Edit document…", bob)
        self.assertNotIn("Add a collaborator",
                         self.bob.get(f"/reports/{report_id}/history").get_data(as_text=True))

        source = self.bob.get(f"/reports/{report_id}/source").get_data(as_text=True)
        self.assertIn("readonly", source)
        self.assertIn("Only the report's owner", source)
        self.assertNotIn("readonly", self.ann.get(f"/reports/{report_id}/source").get_data(True))
        for page in ("document", "versions"):
            self.assertEqual(self.bob.get(f"/reports/{report_id}/{page}").status_code, 403)
            self.assertEqual(self.ann.get(f"/reports/{report_id}/{page}").status_code, 200)

    def test_collaborators(self):
        report_id = self.new_report(self.ann, "Ann's")
        self.assertEqual(self.bob.post(f"/reports/{report_id}/collaborators",
                                       data={"email": "bob@example.com"}).status_code, 403)
        self.ann.post(f"/reports/{report_id}/collaborators", data={"email": "Bob@Example.com"})
        self.assertEqual(store.load_report(self.server.reports, report_id)["collaborators"],
                         ["bob@example.com"])
        self.assertEqual(self.queue_into(self.bob, report_id).status_code, 302)
        self.assertIn("Ann&#39;s", self.bob.get("/reports/").get_data(as_text=True))
        history = self.bob.get(f"/reports/{report_id}/history").get_data(as_text=True)
        self.assertIn("Collaborator", history)

        self.ann.post(f"/reports/{report_id}/collaborators", data={"remove": "bob@example.com"})
        self.assertEqual(self.queue_into(self.bob, report_id).status_code, 403)

    def test_reports_from_before_accounts_are_for_admins(self):
        report_id = models.create_report(self.server.reports, self.server.branch, "Old")
        self.assertEqual(self.queue_into(self.ann, report_id).status_code, 403)
        self.assertEqual(self.queue_into(self.lead, report_id).status_code, 302)

    def test_queue_and_scratch_show_mine(self):
        self.ann.post("/scratch/run", data={"workspace": self.server.branch,
                                            "script": "plain/pass.rst"})
        self.bob.post("/scratch/run", data={"workspace": self.server.branch,
                                            "script": "plain/fail.rst"})
        self.assertIn("plain/pass.rst", self.ann.get("/scratch/").get_data(True))
        self.assertNotIn("plain/fail.rst", self.ann.get("/scratch/").get_data(True))
        self.assertIn("plain/fail.rst", self.ann.get("/scratch/?who=everyone").get_data(True))
        self.assertNotIn("plain/fail.rst", self.ann.get("/runner/").get_data(True))
        self.assertIn("plain/fail.rst", self.ann.get("/runner/?who=everyone").get_data(True))

        # Clearing only clears your own
        for run in models.scratch_runs(self.server.reports):
            store.update_run(self.server.reports, models.SCRATCH, run["id"], outcome="pass")
        self.ann.post("/scratch/clear")
        left = models.scratch_runs(self.server.reports)
        self.assertEqual([r["queued_by"] for r in left], ["bob@example.com"])

    def test_queued_jobs_in_my_reports_show_as_mine(self):
        report_id = self.new_report(self.ann, "Ann's")
        self.ann.post(f"/reports/{report_id}/collaborators", data={"email": "bob@example.com"})
        self.queue_into(self.ann, report_id)
        self.assertIn("plain/pass.rst", self.bob.get("/runner/").get_data(True))


class TestSingleUserHasNoOwners(unittest.TestCase):
    def test_everything_is_everyones(self):
        server = Central(settings=Settings(), scripts=SCRIPTS)
        try:
            http = server.client()
            http.post("/reports/new", data={"name": "R", "workspace": server.branch})
            (report,) = store.list_reports(server.reports)
            self.assertNotIn("owner", report)
            page = http.get("/reports/").get_data(as_text=True)
            self.assertNotIn("Everyone", page)
            self.assertIn(">R<", page)
        finally:
            server.close()
