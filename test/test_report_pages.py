"""A report's pages: its navigation tree by subsystem, requirement and
script, the Runs page it filters, the values touched, and renaming"""

import shutil
import tempfile
import unittest
from pathlib import Path

from automationv3.framework.document import document_title
from automationv3.services.database import connect, init_db
from automationv3.services.reports import store
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
        rst = export.render_rst(export.model(self.root, self.report_id), "f" * 64,
                                "2026-01-01T00:00:00+00:00")
        self.assertIn("untested, no script references it yet", rst)
        self.assertIn("*no tests yet*", rst)
        export.rst_to_latex(rst)

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


class TestPages(ReportPagesTestCase):
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

    def test_every_page_has_the_navigation(self):
        for path in ("", "/runs", "/values", "/history"):
            page = self.get(path)
            self.assertIn('id="report-nav"', page)
            self.assertIn("Brake Pressure Modes", page)  # a script in the tree
            self.assertIn(f"{self.base}/runs?subsystem=BRA#req-BRA-1", page)

    def test_the_runs_page_filters_to_a_subsystem(self):
        page = self.get("/runs?subsystem=BRA")
        self.assertIn('data-subsystem="BRA">', page)
        self.assertIn('data-subsystem="Unassigned" hidden', page)
        self.assertIn('data-subsystem="Other tests" hidden', page)
        self.assertIn('id="req-BRA-1"', page)
        self.assertIn('id="BRA-1--BRA-tc_bra_00004-rst"', page)
        everything = self.get("/runs")
        self.assertIn('id="report-filter" hidden', everything)
        self.assertNotIn('data-subsystem="BRA" hidden', everything)

    def test_the_overview_lists_open_issues_with_why(self):
        page = self.get()
        self.assertIn("Open issues", page)
        self.assertIn("report-why", page)
        self.assertIn("Subsystems", page)
        self.assertIn("Other tests", page)

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
