"""Running scripts locally, without a server, a database file or HTTP"""

import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from automationv3 import cli
from automationv3.services.reports import store
from automationv3.services.worker import Host
from automationv3.services.worker.local import run_locally

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


if __name__ == "__main__":
    unittest.main()
