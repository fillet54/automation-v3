"""Paths written the Windows way ("\\" between folders) name the same
files as the "/" paths the app keys everything by"""

import unittest

from automationv3.framework.closure import resolve
from automationv3.framework.executor import build_env, execute_closure
from automationv3.framework.paths import posix
from automationv3.framework.planning import build_plan
from automationv3.services.workspace import safe_relative_path

from .examples import RVTS

SCRIPT = "LND/tc_lnd_001.rst"


class Recorder:
    def __init__(self):
        self.events = []

    def __getattr__(self, name):
        return lambda **kw: self.events.append((name[3:], kw))


class TestWindowsPaths(unittest.TestCase):
    def test_posix(self):
        from pathlib import PurePosixPath, PureWindowsPath
        self.assertEqual(posix("LND\\tc_lnd_001.rst"), SCRIPT)
        self.assertEqual(posix(PureWindowsPath("LND\\tc_lnd_001.rst")), SCRIPT)
        self.assertEqual(posix(PurePosixPath(SCRIPT)), SCRIPT)

    def test_a_closure_of_a_windows_path_is_the_same_closure(self):
        unix, windows = resolve(RVTS, SCRIPT), resolve(RVTS, "LND\\tc_lnd_001.rst")
        self.assertIn("LND/core.rst", unix.load_order)  # the folder's own core.rst
        self.assertEqual(windows.load_order, unix.load_order)
        self.assertEqual(sorted(windows.files), sorted(unix.files))

    def test_a_load_order_written_on_windows_finds_its_files(self):
        closure = resolve(RVTS, SCRIPT)
        load_order = [p.replace("/", "\\") for p in closure.load_order]
        env = build_env(closure.files, load_order)  # was a KeyError
        self.assertTrue(len(env) > 0)
        outcome = execute_closure(closure.files, load_order, Recorder(),
                                  imports=[p.replace("/", "\\") for p in closure.imports])
        self.assertIsInstance(outcome, str)

    def test_a_plan_names_scripts_with_slashes(self):
        plan = build_plan("ws", RVTS, ["LND\\tc_lnd_001.rst"], scratch=True)
        self.assertEqual([s.script for s in plan.scripts], [SCRIPT])
        self.assertEqual(plan.errors, [])

    def test_workspace_paths_take_backslashes_but_stay_inside(self):
        self.assertEqual(safe_relative_path("LND\\tc_lnd_001.rst"), SCRIPT)
        self.assertIsNone(safe_relative_path("..\\secrets.rst"))
        self.assertIsNone(safe_relative_path("LND\\..\\..\\x.rst"))
