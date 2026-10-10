"""Steps not written yet: (TBD "...")"""

import unittest

from automationv3.framework.statements import get_statements
from automationv3.services.reports import rollup

from .rvt import rvt
from .test_analysis import check
from .test_compose import run


class TestRunning(unittest.TestCase):
    def test_a_run_with_placeholders_is_incomplete(self):
        outcome, rec = run('(Wait 1) (TBD "Engage the autopilot") (Wait 2)')
        self.assertEqual(outcome, "incomplete")
        steps = rec.of("step_end")
        self.assertEqual([s["passed"] for s in steps], [True, True, True])
        self.assertEqual([s.get("placeholders", 0) for s in steps], [0, 1, 0])
        self.assertEqual(steps[1]["stdout"], "")  # the page says "to do" already

    def test_without_placeholders_it_passes(self):
        self.assertEqual(run("(Wait 1)")[0], "pass")

    def test_a_failure_still_fails(self):
        self.assertEqual(run('(TBD "later") (Verify 1 = 2)')[0], "fail")

    def test_inside_code_it_is_a_reported_call_that_comes_out_true(self):
        outcome, rec = run('(if (TBD "Autopilot engaged?") (Wait 1) (Verify false))')
        self.assertEqual(outcome, "incomplete")
        tbd, wait = rec.calls(0)
        self.assertEqual(tbd["block_kind"], "placeholder")
        self.assertEqual(rec.of("step_end")[0]["placeholders"], 1)

    def test_a_precondition_check_holds(self):
        outcome, _ = run('(Precondition "Aircraft trimmed" (TBD "check trim")) (Wait 1)')
        self.assertEqual(outcome, "incomplete")

    def test_incomplete_runs_dont_roll_up_green(self):
        self.assertEqual(rollup.color(["pass", "incomplete"]), "partial")


class TestReading(unittest.TestCase):
    def test_renders_as_a_step_to_be_written(self):
        (statement,) = get_statements(rvt('(TBD "Engage the <autopilot>")'))
        self.assertIn("To be written", statement.html)
        self.assertIn("Engage the &lt;autopilot&gt;", statement.html)

    def test_the_check_counts_them_as_a_warning(self):
        errors, (warning,) = check(rvt('(TBD "a") (step "b" (TBD "c"))'))
        self.assertEqual(errors, [])
        self.assertIn("2 steps are still to be written (TBD)", warning)

    def test_needs_a_description(self):
        (error,) = check(rvt("(TBD)"))[0]
        self.assertIn('(TBD "what the step will do")', error)


if __name__ == "__main__":
    unittest.main()


class TestVehicleManagerExamples(unittest.TestCase):
    """The VM sample scripts against the simulated Vehicle Manager: those
    written in full pass, the others (with TBD steps) are incomplete"""

    def test_every_variation(self):
        import shutil
        import tempfile
        from pathlib import Path

        from automationv3.framework.closure import resolve
        from automationv3.framework.executor import execute_closure
        from automationv3.plugins.sample.demo import Sim
        from automationv3.plugins.vm.sim import VehicleManager

        from .test_compose import Recorder

        root = Path(__file__).resolve().parent / "data" / "rvts"
        scripts = sorted(str(p.relative_to(root)) for p in (root / "VM").rglob("tc_*.rst"))
        self.assertEqual(len(scripts), 66)
        workdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, workdir)
        env, uut = Sim(workdir=workdir), VehicleManager()
        version = uut.list_versions()[-1]
        uut.install(version, env)
        for script in scripts:
            closure = resolve(root, script)
            self.assertEqual(closure.errors, [], script)
            expected = "incomplete" if "(TBD" in (root / script).read_text() else "pass"
            for variation in [v.name for v in closure.variations] or [None]:
                with self.subTest(script=script, variation=variation):
                    uut.start(version, env)
                    recorder = Recorder()
                    handles = {"vm": uut.handle(version, env)}
                    outcome = execute_closure(
                        closure.files, closure.load_order, recorder, closure.imports,
                        variation, bindings=handles, clock=env.clock(handles))
                    failed = [e.get("message") for e in recorder.of("step_end")
                              if not e["passed"]]
                    self.assertEqual(outcome, expected, failed)

    def test_the_known_defect_of_3_1_0_fails_load_shedding(self):
        import shutil
        import tempfile
        from pathlib import Path

        from automationv3.framework.closure import resolve
        from automationv3.framework.executor import execute_closure
        from automationv3.plugins.sample.demo import Sim
        from automationv3.plugins.vm.sim import VehicleManager

        from .test_compose import Recorder

        root = Path(__file__).resolve().parent / "data" / "rvts"
        closure = resolve(root, "VM/EPS/tc_eps_003.rst")
        workdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, workdir)
        env, uut = Sim(workdir=workdir), VehicleManager()
        old = next(v for v in uut.list_versions() if v.id == "3.1.0")
        uut.install(old, env)
        uut.start(old, env)
        handles = {"vm": uut.handle(old, env)}
        outcome = execute_closure(closure.files, closure.load_order, Recorder(),
                                  closure.imports, None, bindings=handles,
                                  clock=env.clock(handles))
        self.assertEqual(outcome, "fail")


if __name__ == "__main__":
    unittest.main()
