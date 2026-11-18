"""The lunar module plugin: versions and builds, installing and booting,
the handle, the connectors, the blocks, and the two environments"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from automationv3.framework import edn
from automationv3.framework.clock import SimClock
from automationv3.framework.executor import execute_closure
from automationv3.framework.uut import Version, environment_types, uut_types
from automationv3.plugins.apollo import Lms, LunarModule, Sim
from automationv3.plugins.apollo.blocks import Connector
from automationv3.plugins.apollo.model.rope import RELEASES, digest

from .rvt import rvt
from .test_compose import Recorder

K = edn.Keyword


class Base(unittest.TestCase):
    environment = Sim

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.env = self.environment(workdir=self.dir / "env")
        self.uut = LunarModule()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def installed(self, version="LUM210"):
        self.uut.install(self.uut.find_version(version), self.env)
        return self.uut.handle(None, self.env)

    def run_script(self, code, lm, core=""):
        recorder = Recorder()
        files = {"core.rst": rvt(core) if core else "", "s.rst": rvt(code)}
        outcome = execute_closure(files, ["core.rst", "s.rst"], recorder,
                                  bindings={"lm": lm}, clock=self.env.clock({"lm": lm}))
        return outcome, recorder


class TestVersions(Base):
    def test_the_plugin_registers_the_uut_and_its_environments(self):
        self.assertIs(uut_types()["lm"], LunarModule)
        self.assertIs(environment_types()["sim"], Sim)
        self.assertIs(environment_types()["lms"], Lms)

    def test_versions_are_the_released_ropes_oldest_first(self):
        versions = self.uut.list_versions()
        self.assertEqual([v.id for v in versions], ["LUM099", "LUM131", "LUM210"])
        self.assertEqual(versions[2].digest, digest(RELEASES["LUM210"]))

    def test_install_and_installed_version(self):
        self.assertIsNone(self.uut.installed_version(self.env))
        version = self.uut.find_version("LUM131")
        self.uut.install(version, self.env)
        self.assertEqual(self.uut.installed_version(self.env), version)
        with self.assertRaises(ValueError):
            self.uut.install(Version("LUM999", "x"), self.env)

    def test_start_boots_a_standard_mission_at_pdi(self):
        lm = self.installed()
        self.assertFalse(lm.booted())
        self.uut.start(None, self.env)
        self.assertTrue(lm.ready(K("standard"), K("pdi")))
        self.assertEqual(lm.read_point("lm.dsky.verb"), 99)

    def test_a_local_build_is_found_uploaded_and_listed_for_scratch_only(self):
        build_dir, repo = self.dir / "build", self.dir / "repo"
        build_dir.mkdir()
        self.assertIsNone(self.uut.find_local_build(build_dir))
        rope = {"revision": "LUM131-fix", "flags": {"extended_missions": True,
                                                    "prop_capacity_from_load": True}}
        (build_dir / "luminary.json").write_text(json.dumps(rope))
        build = self.uut.find_local_build(build_dir)
        self.assertEqual(build.digest, digest(rope))
        self.assertEqual(build.id, f"local-{digest(rope)[:12]}")
        with mock.patch.dict(os.environ, {"AUTOMATION_LM_BUILDS": str(repo)}):
            version = self.uut.upload_build(build)
            self.assertIn(version, self.uut.list_versions())
            self.assertNotIn(version, self.uut.report_versions())
            self.uut.install(version, self.env)
            lm = self.uut.handle(None, self.env)
            lm.boot({K("mission"): K("extended")})
            self.assertEqual(lm.read_point("lm.lgc.prop-percent"), 100.0)


class TestBooting(Base):
    def test_lum099_rejects_an_extended_load(self):
        lm = self.installed("LUM099")
        self.assertEqual(lm.boot({K("mission"): K("extended")}), K("rejected-load"))
        self.assertEqual(lm.boot({K("mission"): K("standard")}), K("accepted"))
        self.assertFalse(lm.supports_extended())

    def test_a_start_point_is_flown_once_and_then_cached(self):
        lm = self.installed()
        lm.boot({K("start"): K("high-gate")})
        self.assertEqual(lm.read_point("lm.lgc.program"), 64)
        cached = list((self.dir / "env" / "lm-starts").iterdir())
        self.assertEqual(len(cached), 1)
        lm.boot({K("start"): K("high-gate"), K("crew"): K("manual")})
        self.assertEqual(len(list((self.dir / "env" / "lm-starts").iterdir())), 1)
        self.assertEqual(lm.config()[K("crew")], K("manual"))
        self.assertTrue(lm.ready(K("standard"), K("high-gate"), K("manual")))
        self.assertFalse(lm.ready(K("standard"), K("high-gate")))
        lm.run_for(1)
        self.assertFalse(lm.at_start())

    def test_the_handle_needs_a_boot(self):
        lm = self.installed()
        with self.assertRaisesRegex(RuntimeError, "StartLM"):
            lm.read_point("lm.lgc.program")


class TestConnectors(Base):
    def setUp(self):
        super().setUp()
        self.lm = self.installed()
        self.lm.boot({K("crew"): K("manual")})

    def test_read_and_read_only(self):
        self.assertEqual(self.lm.read_point("lm.lgc.config.mission"), K("standard"))
        with self.assertRaisesRegex(PermissionError, "read-only"):
            self.lm.set_point("lm.lgc.program", 66)
        with self.assertRaisesRegex(KeyError, "no connector lm.nope"):
            self.lm.read_point("lm.nope")

    def test_panel_switches_take_keywords(self):
        self.lm.set_point("lm.panel.rr-mode", K("auto"))
        self.assertEqual(self.lm.read_point("lm.panel.rr-mode"), K("auto"))
        with self.assertRaisesRegex(ValueError, "must be one of"):
            self.lm.set_point("lm.panel.rr-mode", K("sideways"))

    def test_a_fixed_input_holds_every_step_until_released(self):
        self.lm.fix_point("lm.panel.engine-stop", False)
        self.lm.boot({K("start"): K("low-gate")})  # a new flight forgets fixed values
        self.lm.fix_point("lm.panel.engine-stop", False)
        self.lm.fly_to(K("contact"))
        self.lm.run_for(5)
        self.assertFalse(self.lm.read_point("lm.panel.engine-stop"))  # the crew couldn't
        self.lm.fix_point("lm.bench.bus-load-amps", 200.0)
        self.lm.run_for(1)
        self.assertTrue(self.lm.read_point("lm.cwea.light.battery"))
        self.lm.release_point("lm.bench.bus-load-amps")
        self.lm.run_for(1)
        self.assertEqual(self.lm.read_point("lm.bench.bus-load-amps"), 0.0)
        self.assertFalse(self.lm.read_point("lm.cwea.light.battery"))

    def test_children_for_completion(self):
        top = {c.name for c in Connector.children("")}
        self.assertEqual(top, {"lm"})
        below = {c.name: c for c in Connector.children("lm.panel")}
        self.assertIn("rr-mode", below)
        self.assertEqual(below["rr-mode"].detail, "settable")
        self.assertEqual({c.name: c.detail for c in Connector.children("lm.lgc")}["program"],
                         "read-only")


class TestBlocks(Base):
    CORE = '(def dsky (connector "lm.dsky")) (def lgc (connector "lm.lgc"))'

    def test_a_flight_from_high_gate_to_touchdown(self):
        lm = self.installed()
        outcome, rec = self.run_script('''
            (StartLM {:mission :extended :start :high-gate})
            (Verify lgc.program = 64)
            (FlyTo :touchdown)
            (Verify (connector "lm.landed"))
            (Verify (abs (Read (connector "lm.touchdown.vz"))) <= 3.05)
            (AttachTrajectory "descent")
        ''', lm, self.CORE)
        self.assertEqual(outcome, "pass", rec.events[-5:])
        names = [a["name"] for a in rec.of("attach")]
        self.assertEqual(names, ["descent.csv", "descent.svg"])

    def test_keys_proceed_and_the_dsky(self):
        lm = self.installed()
        outcome, rec = self.run_script('''
            (StartLM {:crew :manual})
            (Verify dsky.flashing)
            (Proceed)
            (RunFor 1)
            (Verify (connector "lm.engine.descent.on"))
            (Verify (.get (Keys "V16N68E") :noun) = 68)
            (Keys "V99E")
            (Verify dsky.light.opr-err)
            (Keys "R")
            (Verify (not (Read dsky.light.opr-err)))
        ''', lm, self.CORE)
        self.assertEqual(outcome, "pass", rec.events[-5:])

    def test_a_wait_runs_the_flight_forward(self):
        lm = self.installed()
        outcome, rec = self.run_script('''
            (StartLM {:start :low-gate :crew :manual})
            (ClickROD 1)
            (Verify lgc.program = 66)
            (Wait (connector "lm.contact") :within 5min :every 1s)
        ''', lm, self.CORE)
        self.assertEqual(outcome, "pass", rec.events[-5:])

    def test_start_fails_for_a_load_the_rope_rejects(self):
        lm = self.installed("LUM099")
        outcome, _ = self.run_script("(StartLM {:mission :extended})", lm)
        self.assertEqual(outcome, "fail")

    def test_click_rod_fails_outside_the_landing_programs(self):
        lm = self.installed()
        outcome, _ = self.run_script("(StartLM {:crew :manual}) (ClickROD 1)", lm)
        self.assertEqual(outcome, "fail")

    def test_blocks_render(self):
        from automationv3.plugins.apollo.blocks import FlyTo, Keys, StartLM
        self.assertIn("ENTR", Keys().as_rst("V16N68E"))
        self.assertIn("Configuration", StartLM().as_rst(edn.Map({K("mission"): K("extended")})))
        self.assertIn(":high-gate", FlyTo().as_rst(K("high-gate")))


class TestLms(Base):
    environment = Lms

    def test_the_flight_runs_with_the_wall_clock_at_its_pace(self):
        now = [1000.0]
        self.uut.install(self.uut.find_version("LUM210"), self.env)
        from automationv3.plugins.apollo.handle import LunarModuleHandle
        lm = LunarModuleHandle(self.uut, self.env, wall=lambda: now[0],
                               sleep=lambda s: now.__setitem__(0, now[0] + s))
        lm.boot({K("crew"): K("manual")})
        self.assertEqual(lm.read_point("lm.time.sim"), 0.0)
        now[0] += 1.0  # one second of wall time is twenty of the flight's
        self.assertEqual(lm.read_point("lm.time.sim"), 20.0)
        lm.run_for(10)
        self.assertGreaterEqual(lm.read_point("lm.time.sim"), 30.0)
        clock = self.env.clock({"lm": lm})
        self.assertIsInstance(clock, SimClock)
        self.assertIsNone(clock.step)

    def test_the_fingerprint_names_the_pace(self):
        self.assertEqual(self.env.fingerprint()["pace"], 20.0)
        self.assertEqual(self.env.settings()["terrain"], True)
