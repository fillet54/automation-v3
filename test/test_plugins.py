"""Plugin functions: discovery, conflicts, analysis and script isolation."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from automationv3.framework import edn, lisp, plugins, value_blocks
from automationv3.framework.closure import resolve
from automationv3.framework.executor import execute_closure, new_env
from automationv3.framework.block import all_blocks, is_abstract
from automationv3.plugins.core import value_blocks as old_value_blocks
from .rvt import rvt


class Recorder:
    def __getattr__(self, name):
        return lambda **kw: None


class TestPluginFunctions(unittest.TestCase):
    def setUp(self):
        plugins.load_plugins()
        self.env = patch.dict(lisp.global_env)
        self.functions = patch.dict(plugins._functions)
        self.env.start()
        self.functions.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.functions.stop)
        self.registry = plugins.PluginRegistry("test-plugin")

    def test_registered_function_executes_and_exposes_its_documentation(self):
        def double(x):
            """Twice the input."""
            return 2 * x
        self.registry.function("test/double", double)
        self.assertEqual(lisp.eval(edn.read("(test/double 3)"), new_env()), 6)
        entry = next(f for f in plugins.registered_functions() if f.name == "test/double")
        self.assertEqual((entry.plugin, entry.doc), ("test-plugin", "Twice the input."))

    def test_duplicate_registration_is_idempotent_only_for_the_same_owner_and_function(self):
        def fn(x):
            return x
        self.registry.function("test/fn", fn)
        self.registry.function("test/fn", fn)
        with self.assertRaisesRegex(ValueError, "already registered by test-plugin"):
            plugins.PluginRegistry("other-plugin").function("test/fn", fn)
        with self.assertRaises(ValueError):
            self.registry.function("test/fn", lambda x: x)

    def test_functions_cannot_replace_builtins_forms_or_blocks(self):
        for name in ["+", "if", "step", "Verify", "Read", "uut", "Precondition"]:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "conflicts"):
                self.registry.function(name, lambda: None)

    def test_invalid_names_and_non_callable_values_are_rejected(self):
        for name in ["", "two words", ":keyword", "42", "(call)"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.registry.function(name, lambda: None)
        with self.assertRaises(TypeError):
            self.registry.function("test/value", 3)

    def test_registered_names_and_arity_are_checked_before_execution(self):
        self.registry.function("test/double", lambda x: 2 * x)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "s.rst"
            path.write_text(rvt("(Verify (test/double 3) = 6)"))
            closure = resolve(root, "s.rst")
            self.assertEqual(closure.errors, [])
            self.assertEqual(execute_closure(closure.files, closure.load_order, Recorder()), "pass")
            path.write_text(rvt("(Verify (test/double 3 4) = 6)"))
            self.assertIn("test/double can't take 2 arguments", " ".join(resolve(root, "s.rst").errors))

    def test_script_definitions_shadow_defaults_without_changing_other_runs(self):
        self.registry.function("test/double", lambda x: 2 * x)
        first, second = new_env(), new_env()
        lisp.eval(edn.read("(defn test/double [x] (* x 3))"), first)
        self.assertEqual(lisp.eval(edn.read("(test/double 2)"), first), 6)
        self.assertEqual(lisp.eval(edn.read("(test/double 2)"), second), 4)

    def test_installed_entry_points_load_automatically_once(self):
        calls = []
        def register(registry):
            calls.append(registry.plugin)
            registry.function("external/double", lambda x: 2 * x)
        entry = SimpleNamespace(name="external-plugin", load=lambda: register)
        with patch.object(plugins, "_loaded", False), \
                patch.object(plugins, "entry_points", return_value=[entry]) as discover:
            plugins.load_plugins()
            plugins.load_plugins()
        discover.assert_called_once_with(group="automationv3.plugins")
        self.assertEqual(calls, ["external-plugin"])
        self.assertEqual(lisp.eval(edn.read("(external/double 4)"), new_env()), 8)

    def test_core_owns_test_helpers_and_vm_uses_the_registration_hook(self):
        self.assertNotIn("group", lisp.standard_env())
        functions = {f.name: f.plugin for f in plugins.registered_functions()}
        self.assertEqual(functions["group"], "automationv3.plugins.core")
        self.assertEqual(functions["connector"], "automationv3.plugins.vm")
        self.assertEqual(lisp.eval(edn.read('(vm/connector "vm.eps")')).path, "vm.eps")

    def test_failed_plugin_registration_rolls_back_functions(self):
        def register(registry):
            registry.function("external/temporary", lambda: 1)
            raise RuntimeError("broken plugin")
        entry = SimpleNamespace(name="broken-plugin", load=lambda: register)
        with patch.object(plugins, "_loaded", False), patch.object(plugins, "_error", None), \
                patch.object(plugins, "entry_points", return_value=[entry]) as discover:
            with self.assertRaisesRegex(
                    plugins.PluginLoadError,
                    "Plugin broken-plugin failed to load: RuntimeError: broken plugin") as raised:
                plugins.load_plugins()
            self.assertEqual(raised.exception.plugin, "broken-plugin")
            self.assertIsInstance(raised.exception.__cause__, RuntimeError)
            self.assertNotIn("external/temporary", lisp.global_env)
            self.assertNotIn("external/temporary", plugins._functions)
            # Remembered: every later use reports it, without loading again
            with self.assertRaises(plugins.PluginLoadError) as again:
                lisp.eval(edn.read("(+ 1 2)"), lisp.Env(outer=lisp.global_env))
            self.assertIs(again.exception, raised.exception)
            discover.assert_called_once()

    def test_an_entry_point_without_a_register_hook_names_the_plugin(self):
        entry = SimpleNamespace(name="hookless", load=lambda: SimpleNamespace())
        with patch.object(plugins, "_loaded", False), patch.object(plugins, "_error", None), \
                patch.object(plugins, "entry_points", return_value=[entry]):
            with self.assertRaisesRegex(plugins.PluginLoadError,
                                        "Plugin hookless failed to load: .*register"):
                plugins.load_plugins()

    def test_startup_reports_a_broken_plugin_and_exits(self):
        from automationv3 import cli
        error = plugins.PluginLoadError("broken-plugin", "Plugin broken-plugin failed to load: "
                                                         "RuntimeError: broken plugin")
        with patch.object(plugins, "_error", error), \
                patch.object(cli, "start_server") as start, \
                self.assertRaises(SystemExit) as exit:
            cli.main(["server"])
        self.assertIn("Plugin broken-plugin failed to load", str(exit.exception.code))
        start.assert_not_called()

    def test_static_analysis_loads_plugin_defaults_in_a_fresh_process(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "s.rst").write_text(rvt('(Verify (ref? (connector "vm.eps")))'))
            result = subprocess.run([sys.executable, "-c",
                "import sys; from automationv3.framework.closure import resolve; "
                "c = resolve(sys.argv[1], 's.rst'); assert not c.errors, c.errors", folder],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_abstract_contracts_can_be_imported_first_in_a_fresh_process(self):
        result = subprocess.run([sys.executable, "-c", "from automationv3.framework import "
                                 "value_blocks; from automationv3.framework.plugins import "
                                 "load_plugins; load_plugins()"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_value_contract_compatibility_imports_are_identical(self):
        for name in ["Read", "SetValue", "SetFixedValue", "ClearFixedValue"]:
            self.assertIs(getattr(value_blocks, name), getattr(old_value_blocks, name))
        self.assertTrue(all(is_abstract(b) for b in all_blocks()
                            if type(b).__module__.startswith("automationv3.framework.")))
