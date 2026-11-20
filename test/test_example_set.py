"""The Apollo example set (automationv3/examples/apollo) does what its
scripts say.

Every script either passes or fails on purpose. This queues the whole set
by requirement on LUM210, in the sim environment, runs it on a worker,
and checks each outcome and the requirement rollup; then the scripts
whose outcome depends on the version, on LUM131 and LUM099.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from automationv3.framework.closure import resolve
from automationv3.services.database import connect, init_db
from automationv3.services.requirements import links
from automationv3.services.reports import rollup, store
from automationv3.services.worker import Host, Worker
from automationv3.services.worker.client import ServerClient
from automationv3.services.workspace import find_worktrees
from automationv3.web.app import create_app

from . import gitutil
from .test_jobs import FlaskSession

EXAMPLE = Path(__file__).resolve().parent.parent / "automationv3" / "examples" / "apollo"
RVTS = EXAMPLE / "rvts"

MISSIONS = ["standard", "extended"]

# script -> its variations (None: it has none). The lms-only script and the
# one that doesn't queue aren't here: they never run in sim.
SCRIPTS = {
    "DSKY/tc_dsky_001.rst": [None],
    "DSKY/tc_dsky_002.rst": [None],
    "DSKY/tc_dsky_003.rst": [None],
    "GDN/tc_gdn_001.rst": [None],
    "GDN/tc_gdn_002.rst": MISSIONS,
    "GDN/tc_gdn_003.rst": MISSIONS,
    "GDN/tc_gdn_004.rst": [None],
    "GDN/tc_gdn_005.rst": [None],
    "GDN/tc_gdn_006.rst": [None],
    "GDN/tc_gdn_007.rst": [None],
    "LND/tc_lnd_001.rst": ["standard from PDI", "standard from high gate",
                           "extended from PDI", "extended from high gate"],
    "LND/tc_lnd_002.rst": [f"seed {n}" for n in range(1, 6)],
    "ABT/tc_abt_001.rst": ["at 12 km", "at 3 km", "at 300 m", "at 30 m"],
    "ABT/tc_abt_002.rst": [None],
    "ABT/tc_abt_003.rst": [None],
    "ALM/tc_alm_001.rst": ["RR at LGC", "RR at AUTO"],
    "ALM/tc_alm_002.rst": [None],
    "ALM/tc_alm_003.rst": MISSIONS,
    "CFG/tc_cfg_001.rst": ["standard load on a standard LM", "extended load on an extended LM",
                           "standard load on an extended LM",
                           "extended load on a standard LM"],
    "CFG/tc_cfg_002.rst": [None],
    "SFC/tc_sfc_001.rst": MISSIONS,
    "SFC/tc_sfc_002.rst": [None],
    "SFC/tc_sfc_003.rst": [None],
    "ECS/tc_ecs_001.rst": [None],
    "ECS/tc_ecs_002.rst": [None],
    "ECS/tc_ecs_003.rst": [None],
}
INCOMPLETE = {"GDN/tc_gdn_007.rst", "ECS/tc_ecs_001.rst", "ECS/tc_ecs_002.rst",
              "ECS/tc_ecs_003.rst"}


def expected_on_lum210():
    expected = {(script, "sim", variation): "incomplete" if script in INCOMPLETE else "pass"
                for script, variations in SCRIPTS.items() for variation in variations}
    # Queued by requirement but skipped: one runs only in lms, one doesn't queue
    expected[("DSKY/tc_dsky_004.rst", None, None)] = "not run"
    expected[("DSKY/tc_dsky_005.rst", None, None)] = "not run"
    return expected


class TestExampleSet(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "reports"
        self.root.mkdir()
        gitdir = self.tmp / "repo"
        shutil.copytree(RVTS, gitdir / "rvts")
        gitutil.create_repo(gitdir)
        self.branch = next(iter(find_worktrees(gitdir / "rvts")))

        app = create_app(DB_PATH=self.tmp / "test.db", REPORTS_PATH=self.root,
                         WORKSPACE_PATH=gitdir / "rvts", TESTING=True)
        with connect(app.config["DB_PATH"]) as conn:
            init_db(conn)
        self.http = app.test_client()

        self.worker = Worker(
            ServerClient("http://server", "http://w1",
                         session=FlaskSession(self.http, "http://server")),
            Host.from_config({"environments": {
                "sim": {"workdir": str(self.tmp / "sim")},
                "lms": {"workdir": str(self.tmp / "lms")},
            }}),
        )
        self.worker.check_in(started=True)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def queue(self, version, **form):
        """Queue in sim on `version`, every variation ticked"""
        ticked = [f"{script}::{variation}" for script, variations in SCRIPTS.items()
                  for variation in variations if variation]
        response = self.http.post("/runner/queue", data={
            "workspace": self.branch, "configured": "1", "environment": "sim",
            "version-lm": version, "variation": ticked, **form})
        self.assertEqual(response.status_code, 302, response.data)
        return response.headers["Location"].rstrip("/").split("/")[-1]

    def run_all(self):
        for _ in range(200):
            if self.worker.work_once() is None:
                return
        self.fail("worker never ran out of work")

    def outcomes(self, report_id):
        report = store.load_report(self.root, report_id)
        runs = store.list_runs(self.root, report_id)
        rows = rollup.combinations(report, runs, lambda run: "pending")
        return report, runs, rows, {(r["script"], r["environment"], r["variation"]): r["state"]
                                    for r in rows}

    def requirements(self):
        conn = connect(":memory:")
        init_db(conn)
        links.refresh(conn, "w", RVTS)
        return sorted(links.scripts_by_requirement(conn, "w"))

    def test_the_whole_set_on_lum210(self):
        report_id = self.queue("LUM210", requirement=self.requirements())
        self.run_all()
        report, runs, rows, outcomes = self.outcomes(report_id)
        expected = expected_on_lum210()
        self.assertEqual({k: v for k, v in outcomes.items() if expected.get(k) != v},
                         {k: v for k, v in expected.items() if outcomes.get(k) != v})

        colors = {r["id"]: r["color"] for r in rollup.requirement_rollup(report, rows)}
        self.assertEqual(colors["LGC-PRP-002"], "green")
        self.assertEqual(colors["MSN-001"], "green")
        self.assertNotIn("red", colors.values())

        # Warm-first scheduling: the LM only boots fresh when nothing warm
        # is left, so most runs reuse it
        modes = [run["mode"] for run in runs]
        self.assertGreater(modes.count("precondition"), modes.count("force"))

    def test_lum131_fails_the_extended_propellant_check(self):
        report_id = self.queue("LUM131", script=["ALM/tc_alm_003.rst", "LND/tc_lnd_001.rst"])
        self.run_all()
        report, _, rows, outcomes = self.outcomes(report_id)
        self.assertEqual(outcomes[("ALM/tc_alm_003.rst", "sim", "extended")], "fail")
        self.assertEqual(outcomes[("ALM/tc_alm_003.rst", "sim", "standard")], "pass")
        self.assertEqual({v for k, v in outcomes.items() if k[0] == "LND/tc_lnd_001.rst"},
                         {"pass"})
        colors = {r["id"]: r["color"] for r in rollup.requirement_rollup(report, rows)}
        self.assertEqual(colors["LGC-PRP-002"], "red")

    def test_lum099_blocks_extended_missions(self):
        report_id = self.queue("LUM099", script=["GDN/tc_gdn_003.rst", "CFG/tc_cfg_002.rst"])
        self.run_all()
        _, _, _, outcomes = self.outcomes(report_id)
        self.assertEqual(outcomes, {
            ("GDN/tc_gdn_003.rst", "sim", "standard"): "pass",
            ("GDN/tc_gdn_003.rst", "sim", "extended"): "blocked",
            ("CFG/tc_cfg_002.rst", "sim", None): "fail",
        })

    def test_the_lms_only_script_is_planned_but_not_run_in_sim(self):
        closure = resolve(RVTS, "DSKY/tc_dsky_004.rst")
        self.assertEqual(closure.environments, ["lms"])
        self.assertEqual(resolve(RVTS, "SFC/tc_sfc_001.rst").environments, ["sim"])
        self.assertEqual(resolve(RVTS, "GDN/tc_gdn_001.rst").environments, ["sim", "lms"])

    def test_lint_example_refuses_to_queue(self):
        closure = resolve(RVTS, "DSKY/tc_dsky_005.rst")
        self.assertEqual(closure.errors,
                         ["DSKY/tc_dsky_005.rst: Precondition Too late to matter "
                          "must come before the first step"])
        response = self.http.post("/runner/queue", data={
            "workspace": self.branch, "script": "DSKY/tc_dsky_005.rst"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"must come before the first step", response.data)

    def test_every_script_is_accounted_for(self):
        scripts = {str(p.relative_to(RVTS)) for p in RVTS.rglob("tc_*.rst")}
        self.assertEqual(scripts - set(SCRIPTS),
                         {"DSKY/tc_dsky_004.rst", "DSKY/tc_dsky_005.rst"})

    def test_every_linked_requirement_is_in_the_specifications(self):
        import json
        import re
        history = json.loads((EXAMPLE / "doors" / "history.json").read_text())
        text = "".join(p.read_text() for p in (EXAMPLE / "doors" / "specs").rglob("*.rst"))
        text += "".join(edit.get("append", "") for run in history["runs"]
                        for edit in run.get("edits", []))
        ids = set(re.findall(r"\.\. requirement:: (\S+)", text))
        self.assertLessEqual(set(self.requirements()), ids)


if __name__ == "__main__":
    unittest.main()
