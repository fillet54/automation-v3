"""The example test set in test/data/rvts does what its scripts say.

Every script either passes or fails on purpose; this queues the whole
set by requirement, runs it on a worker hosting sim and bench, and
checks each outcome and requirement rollup.
"""

import shutil
import tempfile
import unittest
from pathlib import Path


from automationv3.framework.closure import resolve
from automationv3.services.database import connect, init_db
from automationv3.services.reports import rollup, store
from automationv3.services.worker import Host, Worker
from automationv3.services.worker.client import ServerClient
from automationv3.services.workspace import find_worktrees
from automationv3.web.app import create_app

from .data import make_workspaces as gitutil
from .test_jobs import FlaskSession

RVTS = Path(__file__).resolve().parent / "data" / "rvts"

REQUIREMENTS = [f"VMC{s}{n:05d}" for s in ("BRA", "FUE") for n in range(1, 9)]

# (script, environment, variation) -> outcome
EXPECTED = {
    ("BRA/tc_bra_00001.rvt", "sim", None): "pass",
    ("BRA/tc_bra_00002.rvt", "sim", None): "fail",
    ("BRA/tc_bra_00003.rvt", "sim", None): "pass",
    ("BRA/tc_bra_00004.rvt", "sim", "normal"): "pass",
    ("BRA/tc_bra_00004.rvt", "sim", "limp-home"): "pass",
    ("BRA/tc_bra_00004.rvt", "sim", "emergency"): "pass",
    ("BRA/tc_bra_00005.rvt", "sim", None): "pass",
    ("BRA/tc_bra_00005.rvt", "bench", None): "pass",
    ("BRA/tc_bra_00006.rvt", "sim", None): "blocked",
    ("BRA/tc_bra_00008.rvt", "sim", None): "pass",
    ("FUE/tc_fue_00001.rvt", "sim", None): "pass",
    ("FUE/tc_fue_00002.rvt", "sim", "jet-a"): "pass",
    ("FUE/tc_fue_00002.rvt", "sim", "avgas"): "pass",
    ("FUE/tc_fue_00003.rvt", "sim", None): "pass",
    ("FUE/tc_fue_00004.rvt", "sim", None): "pass",
}


class TestExampleSet(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "reports"
        self.root.mkdir()
        gitdir = self.tmp / "repo"
        shutil.copytree(RVTS, gitdir / "rvts")
        gitutil.create_repo(gitdir)
        self.branch = next(iter(find_worktrees(gitdir)))

        app = create_app(DB_PATH=self.tmp / "test.db", REPORTS_PATH=self.root,
                         WORKSPACE_PATH=gitdir, TESTING=True)
        with connect(app.config["DB_PATH"]) as conn:
            init_db(conn)
        self.http = app.test_client()

        self.worker = Worker(
            ServerClient("http://server", "http://w1",
                         session=FlaskSession(self.http, "http://server")),
            Host.from_config({"environments": {
                "sim": {"workdir": str(self.tmp / "sim")},
                "bench": {"workdir": str(self.tmp / "bench")},
            }}),
        )
        self.worker.check_in(started=True)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def queue(self, **form):
        response = self.http.post("/runner/queue", data={"workspace": self.branch, **form})
        self.assertEqual(response.status_code, 302, response.data)
        return response.headers["Location"].rstrip("/").split("/")[-1]

    def run_all(self):
        outcomes = []
        for _ in range(50):
            outcome = self.worker.work_once()
            if outcome is None:
                return outcomes
            outcomes.append(outcome)
        self.fail("worker never ran out of work")

    def test_whole_set_by_requirement(self):
        report_id = self.queue(requirement=REQUIREMENTS)
        self.run_all()

        runs = store.list_runs(self.root, report_id)
        report = store.load_report(self.root, report_id)
        rows = rollup.combinations(report, runs, lambda run: "pending")
        outcomes = {(r["script"], r["environment"], r["variation"]): r["state"]
                    for r in rows}
        self.assertEqual(outcomes, EXPECTED)

        colors = {r["id"]: r["color"]
                  for r in rollup.requirement_rollup(report, rows)}
        self.assertEqual(colors.pop("VMCBRA00007"), "red")      # tc_bra_00002 fails
        self.assertEqual(colors.pop("VMCBRA00005"), "partial")  # tc_bra_00006 blocked
        self.assertEqual(set(colors.values()), {"green"})
        self.assertEqual(len(colors), len(REQUIREMENTS) - 2)

        # Warm-first scheduling: the UUT only starts fresh when nothing warm
        # is left, so most runs reuse it
        modes = [run["mode"] for run in runs]
        self.assertGreater(modes.count("precondition"), modes.count("force"))
        blocked = next(r for r in runs if r["script"] == "BRA/tc_bra_00006.rvt")
        self.assertEqual(blocked["mode"], "force")

    def test_remote_brake_test_needs_newer_demo(self):
        for version, expected in (("1.0.0", "fail"), ("1.1.0", "pass")):
            self.queue(script="BRA/tc_bra_00003.rvt", **{
                "version-demo": version})
            self.assertEqual(self.run_all(), [expected])

    def test_lint_example_refuses_to_queue(self):
        closure = resolve(RVTS, "BRA/tc_bra_00007.rvt")
        self.assertEqual(closure.errors,
                         ["BRA/tc_bra_00007.rvt: Precondition Too late to matter "
                          "must come before the first step"])
        response = self.http.post("/runner/queue", data={
            "workspace": self.branch, "script": "BRA/tc_bra_00007.rvt"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"must come before the first step", response.data)

    def test_every_bra_and_fue_requirement_is_tested(self):
        from automationv3.services.requirements import links
        conn = connect(":memory:")
        init_db(conn)
        links.refresh(conn, "w", RVTS)
        linked = links.scripts_by_requirement(conn, "w")
        self.assertEqual(sorted(linked), REQUIREMENTS)


if __name__ == "__main__":
    unittest.main()
