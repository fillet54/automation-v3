import shutil
import tempfile
import unittest
from pathlib import Path

from automationv3.framework import clock, context, edn, lisp
from automationv3.framework.block import BlockResult, BuildingBlock
from automationv3.framework.closure import resolve
from automationv3.framework.executor import execute_closure
from automationv3.framework.refs import Ref
from automationv3.plugins.core import value_blocks

from .rvt import rvt


class Bench(clock.Clock):
    """Where the tests' Wires point: values by path, and a clock of its
    own, at which values can be scheduled to change"""

    def __init__(self, values=None):
        self.values = dict(values or {})
        self.fixed = {}
        self.time = 0.0
        self.schedule = []  # (time, path, value)
        self.log = []

    def get(self, path):
        if path not in self.values and path not in self.fixed:
            raise KeyError(f"no value at {path}")
        return self.fixed.get(path, self.values.get(path))

    def now(self):
        return self.time

    def sleep(self, seconds):
        self.time += seconds
        for when, path, value in list(self.schedule):
            if when <= self.time:
                self.values[path] = value
                self.schedule.remove((when, path, value))


# The tests' kind of ref, and the blocks that reach it: what a plugin
# provides


class Wire(Ref):
    """A test ref, into the Bench bound as `bench`"""


lisp.global_env["wire"] = Wire


def bench():
    return context.lookup("bench")


class Read(value_blocks.Read):
    ref_type = Wire

    def read(self, ref):
        return bench().get(ref.path)


class SetValue(value_blocks.SetValue):
    ref_type = Wire

    def write(self, ref, value):
        bench().log.append(("set", ref.path, value))
        bench().values[ref.path] = value


class SetFixedValue(value_blocks.SetFixedValue):
    ref_type = Wire

    def fix(self, ref, value):
        bench().log.append(("fix", ref.path, value))
        bench().fixed[ref.path] = value


class ClearFixedValue(value_blocks.ClearFixedValue):
    ref_type = Wire

    def release(self, ref):
        bench().log.append(("clear", ref.path))
        if getattr(bench(), "stuck", False):
            raise RuntimeError("stuck")
        bench().fixed.pop(ref.path, None)


CORE = """
(def cpu1 (wire "sys.cpu1"))
(def cpu2 (wire "sys.cpu2"))
(def cpu (group cpu1 cpu2))
(def nav cpu1.app.nav)
"""

VALUES = {
    "sys.cpu1.app.nav.mode": "run", "sys.cpu2.app.nav.mode": "run",
    "sys.cpu1.app.nav.sol": 1, "sys.cpu2.app.nav.sol": 2,
    "sys.cpu1.role": "primary", "sys.cpu2.role": "backup",
    "sys.cpu1.cmd": 5, "sys.cpu2.cmd": 6,
    "sys.cpu1.echo": 5, "sys.cpu2.echo": 6,
    "sys.cpu1.ok": True, "sys.cpu2.ok": False,
}


class Recorder:
    def __init__(self):
        self.events = []

    def __getattr__(self, name):
        return lambda **kw: self.events.append((name[3:], kw))

    def of(self, kind):
        return [kw for k, kw in self.events if k == kind]

    def steps(self):
        return self.of("step_end")


def run(script, values=VALUES, core=CORE, bench=None):
    bench = bench or Bench(values)
    recorder = Recorder()
    files = {"core.rst": rvt(core), "s.rst": rvt(script)}
    outcome = execute_closure(files, ["core.rst", "s.rst"], recorder,
                              bindings={"bench": bench}, clock=bench)
    return outcome, recorder, bench


def check(script, core=CORE):
    """Errors and warnings of the script, by static analysis"""
    root = Path(tempfile.mkdtemp())
    try:
        (root / "core.rst").write_text(rvt(core))
        (root / "s.rst").write_text(script)
        closure = resolve(root, "s.rst")
        return closure.errors + closure.warnings
    finally:
        shutil.rmtree(root)


class TestValues(unittest.TestCase):
    def test_dotted_names_extend_a_ref(self):
        c = Wire("sys.cpu1").__named__("cpu1")
        child = c.__child__("app.mode")
        self.assertEqual(child.path, "sys.cpu1.app.mode")
        self.assertEqual(child.label, "cpu1.app.mode")

    def test_a_def_names_the_ref(self):
        outcome, rec, _ = run("(Verify nav.mode = \"run\")")
        self.assertEqual(outcome, "pass")
        self.assertEqual(rec.steps()[0]["stdout"], 'nav.mode ("run") = "run"')

    def test_a_ref_passes_like_any_value(self):
        script = """
(defn mode-of [sys] (Read sys.app.nav.mode))
(Verify (mode-of cpu2) = "run")
"""
        outcome, _, _ = run(script)
        self.assertEqual(outcome, "pass")

    def test_dotted_name_on_a_non_connector(self):
        outcome, rec, _ = run("(def n 3) (Verify n.x = 1)")
        self.assertEqual(outcome, "error")
        self.assertIn("n isn't a ref", rec.steps()[-1]["message"])

    def test_time_literals_are_seconds(self):
        self.assertEqual(edn.read("5000ms"), 5.0)
        self.assertEqual(edn.read("2min"), 120.0)
        self.assertEqual(edn.read("1h"), 3600.0)
        self.assertEqual(edn.read("5seconds"), 5.0)
        self.assertEqual(edn.writes(edn.read("[500ms 2]")), "[500ms 2]")


class TestRead(unittest.TestCase):
    def test_read_one(self):
        outcome, rec, _ = run("(Verify (= (Read cpu1.role) \"primary\"))")
        self.assertEqual(outcome, "pass")

    def test_read_group_gives_a_map_by_member(self):
        outcome, rec, _ = run('(Verify (Read cpu.role) = {:cpu1 "primary" :cpu2 "backup"})')
        self.assertEqual(outcome, "pass")


class TestVerify(unittest.TestCase):
    def test_group_checks_every_member(self):
        outcome, rec, _ = run('(Verify cpu.app.nav.mode = "run")')
        self.assertEqual(outcome, "pass")
        self.assertEqual(rec.steps()[0]["stdout"],
                         'cpu1.app.nav.mode ("run") = "run"\n'
                         'cpu2.app.nav.mode ("run") = "run"')

    def test_group_fails_if_one_member_does(self):
        outcome, rec, _ = run('(Verify cpu.role = "primary")')
        self.assertEqual(outcome, "fail")
        self.assertIn('cpu2.role ("backup") = "primary"  <- no', rec.steps()[0]["stdout"])

    def test_verify_all_is_verify(self):
        self.assertEqual(run('(VerifyAll cpu.role = "primary")')[0], "fail")

    def test_verify_any(self):
        self.assertEqual(run('(VerifyAny cpu.role = "primary")')[0], "pass")
        self.assertEqual(run('(VerifyAny cpu.role = "spare")')[0], "fail")
        self.assertEqual(run("(VerifyAny cpu.ok)")[0], "pass")
        self.assertEqual(run("(Verify cpu.ok)")[0], "fail")

    def test_ref_against_ref(self):
        self.assertEqual(run("(Verify cpu1.cmd = cpu1.echo)")[0], "pass")
        self.assertEqual(run("(Verify cpu1.cmd = cpu2.echo)")[0], "fail")

    def test_groups_pair_by_position(self):
        self.assertEqual(run("(Verify cpu.cmd = cpu.echo)")[0], "pass")
        self.assertEqual(run("(Verify cpu.cmd < cpu.app.nav.sol)")[0], "fail")

    def test_group_against_single_ref(self):
        self.assertEqual(run("(Verify cpu.cmd >= cpu1.echo)")[0], "pass")

    def test_groups_of_different_sizes(self):
        core = CORE + '(def trio (group cpu1 cpu2 (wire "sys.cpu3")))'
        outcome, rec, _ = run("(Verify cpu.cmd = trio.cmd)", core=core)
        self.assertEqual(outcome, "error")
        self.assertIn("can't pair a group of 2 with a group of 3", rec.steps()[0]["message"])

    def test_same(self):
        self.assertEqual(run("(Verify (same? cpu.app.nav.mode))")[0], "pass")
        self.assertEqual(run("(Verify (same? cpu.role))")[0], "fail")

    def test_plain_values_still_work(self):
        outcome, rec, _ = run("(Verify 60 <= 80)")
        self.assertEqual(rec.steps()[0]["stdout"], "60 <= 80")
        self.assertEqual(run("(Verify (= 1 1))")[0], "pass")


class TestWait(unittest.TestCase):
    def bench(self, *schedule):
        bench = Bench(VALUES)
        bench.schedule = list(schedule)
        return bench

    def test_waits_until_it_holds(self):
        bench = self.bench((3, "sys.cpu1.role", "backup"))
        outcome, rec, _ = run('(Wait cpu1.role = "backup" :within 5s)', bench=bench)
        self.assertEqual(outcome, "pass")
        self.assertTrue(rec.steps()[0]["stdout"].startswith("after 3"))

    def test_times_out(self):
        bench = self.bench((30, "sys.cpu1.role", "backup"))
        outcome, rec, _ = run('(Wait cpu1.role = "backup" :within 5s)', bench=bench)
        self.assertEqual(outcome, "fail")
        self.assertTrue(rec.steps()[0]["stdout"].startswith("not within 5s"))
        self.assertAlmostEqual(bench.time, 5.0)

    def test_within_is_optional(self):
        bench = self.bench((30, "sys.cpu1.role", "backup"))
        outcome, rec, _ = run('(Wait cpu1.role = "backup")', bench=bench)
        self.assertEqual(outcome, "fail")
        self.assertIn("not within 10s", rec.steps()[0]["stdout"])

    def test_script_default_timeout(self):
        bench = self.bench((30, "sys.cpu1.role", "backup"))
        outcome, _, _ = run('(Wait cpu1.role = "backup")', bench=bench,
                            core=CORE + "(def wait-timeout 1min)")
        self.assertEqual(outcome, "pass")

    def test_every(self):
        bench = self.bench((2.5, "sys.cpu1.role", "backup"))
        run('(Wait cpu1.role = "backup" :within 10s :every 1s)', bench=bench)
        self.assertAlmostEqual(bench.time, 3.0)

    def test_wait_all_needs_every_member(self):
        bench = self.bench((2, "sys.cpu2.role", "primary"))
        outcome, _, _ = run('(WaitAll cpu.role = "primary" :within 5s)', bench=bench)
        self.assertEqual(outcome, "pass")
        self.assertAlmostEqual(bench.time, 2.0)

    def test_wait_any(self):
        bench = self.bench((2, "sys.cpu2.role", "spare"))
        outcome, _, _ = run('(WaitAny cpu.role = "spare" :within 5s)', bench=bench)
        self.assertEqual(outcome, "pass")

    def test_wait_same(self):
        bench = self.bench((4, "sys.cpu2.app.nav.sol", 1))
        outcome, _, _ = run("(WaitSame cpu.app.nav.sol :within 5s)", bench=bench)
        self.assertEqual(outcome, "pass")
        self.assertAlmostEqual(bench.time, 4.0)

    def test_wait_a_time(self):
        outcome, rec, bench = run("(Wait 2s) (Wait 500ms) (Wait 1)")
        self.assertEqual(outcome, "pass")
        self.assertAlmostEqual(bench.time, 3.5)
        self.assertEqual(rec.steps()[0]["stdout"], "waited 2s")

    def test_polled_calls_are_not_reported(self):
        core = CORE + '(defn role [] (Read cpu1.role))'
        bench = self.bench((3, "sys.cpu1.role", "backup"))
        outcome, rec, _ = run('(Wait (role) = "backup" :within 5s)', bench=bench, core=core)
        self.assertEqual(outcome, "pass")
        self.assertEqual(rec.of("call_end"), [])

    def test_bad_option(self):
        outcome, rec, _ = run('(Wait cpu1.role = "x" :within "soon")')
        self.assertEqual(outcome, "error")
        self.assertIn(":within takes a time", rec.steps()[0]["message"])


class TestWrites(unittest.TestCase):
    def test_set_value(self):
        outcome, _, bench = run("(SetValue cpu.cmd 9) (Verify cpu.cmd = 9)")
        self.assertEqual(outcome, "pass")
        self.assertEqual(bench.log, [("set", "sys.cpu1.cmd", 9), ("set", "sys.cpu2.cmd", 9)])

    def test_fixed_values_are_released_at_the_end(self):
        outcome, rec, bench = run("(SetFixedValue cpu1.cmd 1) (Verify cpu1.cmd = 1)")
        self.assertEqual(outcome, "pass")
        self.assertEqual(bench.log[-1], ("clear", "sys.cpu1.cmd"))
        (cleanup,) = rec.of("cleanup")
        self.assertEqual(cleanup["description"], "ClearFixedValue cpu1.cmd")
        self.assertTrue(cleanup["passed"])
        # Released before the run ends
        kinds = [k for k, _ in rec.events]
        self.assertLess(kinds.index("cleanup"), kinds.index("procedure_end"))

    def test_released_even_when_the_script_fails(self):
        outcome, _, bench = run("(SetFixedValue cpu.cmd 1) (Verify cpu1.cmd = 2)")
        self.assertEqual(outcome, "fail")
        self.assertEqual(bench.fixed, {})
        self.assertEqual(bench.log[-2:], [("clear", "sys.cpu2.cmd"), ("clear", "sys.cpu1.cmd")])

    def test_cleared_by_the_script_is_not_cleared_again(self):
        outcome, rec, bench = run("(SetFixedValue cpu1.cmd 1) (ClearFixedValue cpu1.cmd)")
        self.assertEqual(outcome, "pass")
        self.assertEqual(rec.of("cleanup"), [])
        self.assertEqual(bench.log.count(("clear", "sys.cpu1.cmd")), 1)

    def test_a_failing_cleanup_makes_the_run_an_error(self):
        stuck = Bench(VALUES)
        stuck.stuck = True
        outcome, rec, _ = run("(SetFixedValue cpu1.cmd 1)", bench=stuck)
        self.assertEqual(outcome, "error")
        self.assertIn("stuck", rec.of("cleanup")[0]["message"])


class TestTracking(unittest.TestCase):
    def test_touched_refs_are_reported_once_per_step(self):
        script = '(Wait cpu1.role = "primary") (SetValue cpu.cmd 1) (Verify cpu.cmd = 1)'
        _, rec, _ = run(script)
        touched = [(e["index"], e["path"], e["operation"]) for e in rec.of("ref")]
        self.assertEqual(touched, [
            (0, "sys.cpu1.role", "read"),
            (1, "sys.cpu1.cmd", "set"), (1, "sys.cpu2.cmd", "set"),
            (2, "sys.cpu1.cmd", "read"), (2, "sys.cpu2.cmd", "read"),
        ])
        self.assertEqual(rec.of("ref")[0]["name"], "cpu1.role")
        self.assertEqual(rec.of("ref")[0]["type"], "Wire")


# Resolving blocks by the values of their arguments


class Plug(Ref):
    """A second kind of ref, with blocks of its own"""


class Twin(Ref):
    """A kind of ref two blocks claim: an ambiguous call"""


lisp.global_env.update({"plug": Plug, "twin": Twin})


class PlugRead(value_blocks.Read):
    ref_type = Plug

    def name(self):
        return "Read"

    def read(self, ref):
        return f"plug {ref.path}"


class TwinReadA(value_blocks.Read):
    ref_type = Twin

    def name(self):
        return "Read"

    def read(self, ref):
        return "a"


class TwinReadB(TwinReadA):
    def read(self, ref):
        return "b"


class Describe(BuildingBlock):
    """Takes a number"""

    def check_syntax(self, *values):
        return len(values) == 1 and isinstance(values[0], (int, float))

    def execute(self, n):
        return BlockResult(True, stdout=f"number {n}")


class DescribeText(BuildingBlock):
    """Takes text: the same call name, chosen by the value's type"""

    def name(self):
        return "Describe"

    def check_syntax(self, *values):
        return len(values) == 1 and isinstance(values[0], str)

    def execute(self, s):
        return BlockResult(True, stdout=f"text {s}")


class Probe(BuildingBlock):
    """Documented, but no plugin implements it"""

    abstract = True

    def usage(self):
        return "(Probe ref)"


class TestResolution(unittest.TestCase):
    def test_check_syntax_sees_values(self):
        core = CORE + '(def n 3) (def s "x")'
        outcome, rec, _ = run("(Describe n) (Describe s) (Describe (+ 1 1))", core=core)
        self.assertEqual(outcome, "pass")
        self.assertEqual([e["stdout"] for e in rec.steps()], ["number 3", "text x", "number 2"])

    def test_each_kind_of_ref_finds_its_own_read(self):
        outcome, rec, _ = run('(Verify (Read (plug "p.q")) = "plug p.q") (Verify cpu1.role = "primary")')
        self.assertEqual(outcome, "pass", rec.steps())

    def test_two_blocks_accepting_a_unique_call_is_an_error(self):
        outcome, rec, _ = run('(Read (twin "t"))')
        self.assertEqual(outcome, "error")
        message = rec.steps()[0]["message"]
        self.assertIn("Read is accepted by 2 blocks", message)
        self.assertIn("TwinReadA", message)
        self.assertIn("TwinReadB", message)

    def test_ambiguous_inside_verify(self):
        outcome, rec, _ = run('(Verify (twin "t") = "a")')
        self.assertEqual(outcome, "error")
        self.assertIn("accepted by 2 blocks", rec.steps()[0]["message"])

    def test_no_block_accepts_the_values(self):
        outcome, rec, _ = run('(Read "sys.cpu1")')
        self.assertEqual(outcome, "error")
        self.assertIn("no form of Read accepts", rec.steps()[0]["message"])
        self.assertIn("given str", rec.steps()[0]["message"])

    def test_arguments_are_evaluated_once(self):
        core = CORE + "(defn role [] (Read cpu1.role))"
        _, rec, _ = run('(Describe (count (role)))', core=core)
        self.assertEqual(len(rec.of("call_end")), 1)

    def test_abstract_blocks_are_never_called(self):
        outcome, rec, _ = run("(Probe cpu1)")
        self.assertEqual(outcome, "error")
        self.assertIn("no plugin implements Probe", rec.steps()[0]["message"])

    def test_forms_blocks_still_match_on_forms(self):
        # TBD takes its text as written; Verify its check
        self.assertEqual(run('(TBD "later") (Verify 1 = 1)')[0], "incomplete")


class TestAnalysis(unittest.TestCase):
    def test_unknown_connector_root(self):
        (error,) = check(rvt("(Verify cpuu.app.mode = 1)"))
        self.assertIn("unknown name cpuu", error)
        self.assertIn("did you mean cpu", error)

    def test_known_roots_and_params(self):
        script = rvt('(defn m [sys] (Verify sys.app.mode = 1))\n(m cpu1)\n'
                     '(Wait nav.mode = 1 :within 5s :every 1s)\n(WaitSame cpu.x)')
        self.assertEqual(check(script), [])

    def test_unimplemented_block(self):
        (error,) = check(rvt("(Probe cpu1)"))
        self.assertIn("no plugin implements Probe", error)

    def test_value_blocks_are_checked_by_count(self):
        (error,) = check(rvt("(Describe 1 2)"))
        self.assertIn("no form of Describe matches", error)
        self.assertEqual(check(rvt("(Describe nav)")), [])

    def test_wait_forms_are_checked(self):
        (error,) = check(rvt("(Wait (nope) = 1 :within 5s)"))
        self.assertIn("unknown name nope", error)


if __name__ == "__main__":
    unittest.main()


class TestVehicleManagerPoints(unittest.TestCase):
    def setUp(self):
        from automationv3.framework.uut import Environment
        from automationv3.plugins.vm.sim import VehicleManager
        self.dir = Path(tempfile.mkdtemp())
        env = Environment()
        env.workdir = self.dir
        uut = VehicleManager()
        uut.install(uut.list_versions()[-1], env)
        self.vm = uut.handle(None, env)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_read_and_read_only(self):
        self.assertEqual(self.vm.read_point("vm.mode.current"), edn.Keyword("standby"))
        with self.assertRaisesRegex(PermissionError, "read-only"):
            self.vm.set_point("vm.eps.shed", "none")
        with self.assertRaisesRegex(KeyError, "no connector vm.nope"):
            self.vm.read_point("vm.nope")

    def test_fixed_values_hold_every_frame(self):
        self.vm.fix_point("vm.bench.battery.soc", 30.0)
        self.vm.discharge_to(10.0, 60.0)
        self.vm.run_for(5)
        self.assertEqual(self.vm.read_point("vm.eps.soc"), 30.0)
        self.vm.release_point("vm.bench.battery.soc")
        self.vm.discharge_to(10.0, 60.0)
        self.vm.run_for(5)
        self.assertLess(self.vm.read_point("vm.eps.soc"), 30.0)

    def test_releasing_a_fault_clears_it(self):
        self.vm.fix_point("vm.bench.attitude-error", 15.0)
        self.vm.release_point("vm.bench.attitude-error")
        self.assertEqual(self.vm.read_point("vm.bench.attitude-error"), 0.0)

    def test_advancing_runs_whole_frames(self):
        start = self.vm.read_point("vm.obc.sim-time")
        for _ in range(15):
            self.vm.advance(0.1)
        self.assertAlmostEqual(self.vm.read_point("vm.obc.sim-time") - start, 1.5)
        self.assertEqual(self.vm.read_point("vm.obc.time") - start, 1.0)
