"""A report's pages: its navigation tree by subsystem, requirement and
script, the Runs page it filters, the values touched, and renaming"""

import shutil
import tempfile
import unittest
from pathlib import Path

from automationv3.framework.document import document_title
from automationv3.services.database import connect, init_db
from automationv3.services.reports import export, store
from automationv3.services.worker import Host
from automationv3.services.worker.local import run_locally
from automationv3.web import report_view
from automationv3.web.app import create_app

from .data import make_workspaces as gitutil

RVTS = Path(__file__).resolve().parent / "data" / "rvts"


class TestDocumentTitle(unittest.TestCase):
    def test_the_first_heading_overlined_or_not(self):
        self.assertEqual(document_title("=====\nBrake\n=====\nText"), "Brake")
        self.assertEqual(document_title("Intro\n\nBrakes\n------\n"), "Brakes")
        self.assertIsNone(document_title("Too long\n---\n"))
        self.assertIsNone(document_title("(Wait 1)"))


class ReportPagesTestCase(unittest.TestCase):
    """A report tracking BRA-1 (a script that passes) and BRA-2 (none run),
    with a failing script added on its own"""

    @classmethod
    def setUpClass(cls):
        cls.source = Path(tempfile.mkdtemp())
        host = Host.from_config({"environments": {"sim": {"workdir": str(cls.source / "sim")}}})
        cls.report_id, _ = run_locally(
            RVTS, ["BRA/tc_bra_00004.rst", "BRA/tc_bra_00003.rst"], cls.source / "reports",
            host, versions={"demo": "1.0.0"})
        store.update_report(
            cls.source / "reports", cls.report_id, name="Brakes",
            requirements={"BRA-1": ["BRA/tc_bra_00004.rst"], "BRA-2": ["BRA/missing.rst"]},
            requirement_snapshots={"BRA-1": {"text": "The brakes shall hold.",
                                             "subsystem": "BRA"}})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.source)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "reports"
        shutil.copytree(self.source / "reports", self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def view(self, lookup=None):
        report = store.load_report(self.root, self.report_id)
        runs = store.list_runs(self.root, self.report_id)
        return report_view.build(self.root, report, runs, lambda run: "pending", lookup)


class TestTree(ReportPagesTestCase):
    def test_requirements_group_by_subsystem_with_untracked_scripts_last(self):
        view = self.view()
        self.assertEqual([g["name"] for g in view["groups"]], ["BRA", "Unassigned"])
        (bra1,) = view["groups"][0]["requirements"]
        self.assertEqual((bra1["id"], bra1["dot"], bra1["issues"]), ("BRA-1", "pass", 0))
        self.assertEqual(bra1["text"], "The brakes shall hold.")
        (script,) = bra1["scripts"]
        self.assertEqual(script["title"], "Brake Pressure Modes")
        self.assertEqual(len(script["rows"]), 3)  # its variations
        self.assertEqual(script["anchor"], "BRA-1--BRA-tc_bra_00004-rst")

        (bra2,) = view["groups"][1]["requirements"]
        self.assertEqual((bra2["dot"], bra2["issues"]), ("none", 1))
        self.assertEqual(bra2["scripts"][0]["rows"][0]["state"], "not run")

        other = view["other"]
        self.assertEqual([s["script"] for s in other["scripts"]], ["BRA/tc_bra_00003.rst"])
        self.assertEqual(other["dot"], "fail")
        self.assertEqual(view["dot"], "fail")

    def test_a_requirement_without_tests_is_untested(self):
        report = store.load_report(self.root, self.report_id)
        store.update_report(self.root, self.report_id,
                            requirements={**report["requirements"], "BRA-3": []},
                            requirement_snapshots={
                                **report["requirement_snapshots"],
                                "BRA-3": {"text": "", "subsystem": "BRA"}})
        view = self.view()
        bra = view["groups"][0]
        (bra3,) = [r for r in bra["requirements"] if r["id"] == "BRA-3"]
        self.assertEqual((bra3["color"], bra3["dot"], bra3["scripts"]),
                         ("untested", "none", []))
        self.assertEqual((bra["untested"], bra["issues"]), (1, 1))
        self.assertEqual([r["id"] for r in view["untested"]], ["BRA-3"])

        from automationv3.services.reports import export
        from automationv3.documents import core
        context = export.context(self.root, self.report_id)
        document = export.render_document(context, export.source(self.root, self.report_id))
        html = core.write(document, "html5")["body"]
        self.assertIn("untested, no script references it yet", html)
        self.assertIn("<em>no tests yet</em>", html)

    def test_a_failure_says_where_and_why(self):
        view = self.view()
        (row,) = view["other"]["scripts"][0]["rows"]
        self.assertEqual(row["state"], "fail")
        self.assertIn("step", row["why"])
        self.assertIn(row, view["issues"])

    def test_requirements_the_report_didnt_record_are_looked_up(self):
        view = self.view(lambda ids: {"BRA-2": ("Stops.", "BRK")})
        self.assertEqual([g["name"] for g in view["groups"]], ["BRA", "BRK"])
        self.assertEqual(view["groups"][1]["requirements"][0]["text"], "Stops.")

    def test_a_group_takes_its_worst_dot(self):
        self.assertEqual(report_view.worst(["pass", "partial", "running"]), "running")
        self.assertEqual(report_view.worst(["pass", "running", "fail"]), "fail")
        self.assertEqual(report_view.worst([]), "none")

    def test_values_group_by_the_first_two_parts_of_their_path(self):
        group = report_view.connector_group
        self.assertEqual(group("vm.eps.line.bus-computer.on"), "vm.eps")
        self.assertEqual(group("bench.sun"), "bench")
        connectors = report_view.connectors([
            {"path": "vm.eps.soc", "operations": ["read"]},
            {"path": "vm.eps.shed", "operations": ["read", "fix"]},
            {"path": "vm.mode.current", "operations": ["read"]},
        ])
        self.assertEqual([(c["name"], c["fixed"]) for c in connectors],
                         [("vm.eps", 1), ("vm.mode", 0)])
        self.assertEqual(connectors[0]["refs"][0]["path"], "vm.eps.shed")  # fixed first


class PagesTestCase(ReportPagesTestCase):
    """The report's pages, served"""

    def setUp(self):
        super().setUp()
        gitdir = self.tmp / "repo"
        (gitdir / "rvts").mkdir(parents=True)
        (gitdir / "rvts" / "a.rst").write_text("(Wait 1)")
        gitutil.create_repo(gitdir)
        with connect(self.tmp / "test.db") as conn:
            init_db(conn)
        app = create_app(DB_PATH=self.tmp / "test.db", REPORTS_PATH=self.root,
                         WORKSPACE_PATH=gitdir, TESTING=True)
        self.http = app.test_client()
        self.base = f"/reports/{self.report_id}"

    def get(self, path=""):
        response = self.http.get(self.base + path)
        self.assertEqual(response.status_code, 200, path)
        return response.get_data(True)


class TestPages(PagesTestCase):
    def test_every_page_has_the_navigation(self):
        for path in ("", "/values", "/history"):
            page = self.get(path)
            self.assertIn('id="report-nav"', page)
            self.assertIn("Brake Pressure Modes", page)  # a script in the tree
            self.assertIn(f"{self.base}?subsystem=BRA#req-bra-1", page)

    def test_the_document_narrows_to_a_subsystem(self):
        page = self.get("?subsystem=BRA")
        self.assertIn('id="report-filter"', page)
        self.assertIn('id="req-bra-1"', page)
        self.assertNotIn('id="req-bra-2"', page)  # Unassigned
        everything = self.get()
        self.assertNotIn('id="report-filter"', everything)
        self.assertIn('id="req-bra-2"', everything)
        # the Runs page it replaces sends its links here
        response = self.http.get(self.base + "/runs?subsystem=BRA")
        self.assertEqual(response.headers["Location"], self.base + "?subsystem=BRA")

    def test_the_overview_lists_open_issues_with_why(self):
        page = self.get()
        self.assertIn("Open issues", page)
        self.assertRegex(page, r"ui-outcome--fail.*Failed</span> at step")
        self.assertIn("Requirements", page)
        self.assertIn('href="/reports/', page)  # combinations link their runs

    def test_the_list_of_reports_sums_each_one_up(self):
        page = self.http.get("/reports/").get_data(True)
        self.assertNotIn("Covers", page)
        self.assertIn("1 / 2 green", page)  # BRA-1 green, BRA-2 not run
        self.assertIn("3 / 4", page)  # combinations passed
        self.assertIn('flex-grow: 1;', page)  # the requirements bar
        store.set_frozen(self.root, self.report_id, True)
        self.assertIn("Frozen", self.http.get("/reports/").get_data(True))

    def test_rename_in_place_and_not_when_frozen(self):
        response = self.http.post(self.base + "/rename",
                                  data={"name": "Brakes, build 7", "next": self.base + "/runs"})
        self.assertEqual(response.headers["Location"], self.base + "/runs")
        self.assertIn("Brakes, build 7", self.get())
        response = self.http.post(self.base + "/rename",
                                  data={"name": "x", "next": "https://elsewhere.example"})
        self.assertEqual(response.headers["Location"], self.base)

        store.set_frozen(self.root, self.report_id, True)
        self.assertNotIn("data-rename", self.get())
        response = self.http.post(self.base + "/rename", data={"name": "Other"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(store.load_report(self.root, self.report_id)["name"], "x")


if __name__ == "__main__":
    unittest.main()


class TestDocumentPages(PagesTestCase):
    def test_the_document_is_the_reports_own_rst(self):
        response = self.http.post(self.base + "/source", data={
            "source": "Why\n===\n\nCovers :report:`requirements` requirements.\n\n"
                      ".. results::\n   :state: pass\n"})
        self.assertEqual(response.status_code, 302)
        page = self.get()
        self.assertIn("Covers 2 requirements.", page)
        self.assertIn("tc_bra_00004.rst / sim / normal", page)
        self.assertIn(".. results::", export.source(self.root, self.report_id))

    def test_the_editor_previews_what_it_would_show(self):
        editor = self.get("/source")
        self.assertIn(".. report-summary::", editor)  # the report's document
        self.assertIn('hx-post="' + self.base + '/preview"', editor)
        preview = self.http.post(self.base + "/preview", data={
            "source": "Ran :report:`runs` runs.\n\n.. nope::\n"}).get_data(True)
        self.assertIn("Ran 4 runs.", preview)
        self.assertIn("Unknown directive type", preview)  # problems listed

    def test_each_block_refreshes_itself_while_runs_are_in_progress(self):
        page = self.get()
        self.assertNotIn("hx-get=\"" + self.base + "/block/", page)  # all finished
        block = self.http.get(self.base + "/block/2")
        self.assertEqual(block.status_code, 200)
        self.assertIn('id="block-2"', block.get_data(True))
        self.assertNotIn("hx-trigger", block.get_data(True))  # finished: it stops
        self.assertEqual(self.http.get(self.base + "/block/99").status_code, 404)
        store.update_run(self.root, self.report_id, store.list_runs(
            self.root, self.report_id)[0]["id"], outcome=None)
        page = self.get()
        self.assertIn(f'hx-get="{self.base}/block/2"', page)

    def test_a_frozen_documents_source_is_read_only(self):
        store.set_frozen(self.root, self.report_id, True)
        self.assertIn("readonly", self.get("/source"))
        response = self.http.post(self.base + "/source", data={"source": "x"})
        self.assertEqual(response.status_code, 409)
