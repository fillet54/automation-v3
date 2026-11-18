"""The console's kernel: commands against a live lunar module, kept
between them"""

import shutil
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from automationv3.framework import clock, context
from automationv3.plugins.apollo import Sim
from automationv3.services.worker import Host
from automationv3.services.worker.kernel import Kernel, KernelError, find_form

from .examples import RVTS
from .rvt import doc, rvt

SCRIPT = doc(
    "Console test\n============",
    rvt('''
        (variations "mission"
          ["standard" [:standard]
           "extended" [:extended]])
    '''),
    rvt('''
        (defn twice [x] (* 2 x))
    ''', "definitions"),
    rvt('''
        (Verify (twice 2) = 4)
    '''),
)


class KernelTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.root = self.dir / "rvts"
        (self.root / "T").mkdir(parents=True)
        shutil.copy(RVTS / "core.rst", self.root / "core.rst")
        (self.root / "T" / "tc.rst").write_text(SCRIPT)
        self.host = Host({"sim": Sim(workdir=self.dir / "sim")})
        self.kernels = []

    def tearDown(self):
        for kernel in self.kernels:
            kernel.close()
            kernel.wait_idle(5)
        shutil.rmtree(self.dir)

    def kernel(self, **options):
        kernel = Kernel(self.host, self.root, "T/tc.rst", files_dir=self.dir / "files",
                        **options)
        self.kernels.append(kernel)
        kernel.open()
        self.done(kernel)
        return kernel

    def done(self, kernel, timeout=60):
        self.assertTrue(kernel.wait_idle(timeout), "the kernel didn't finish")

    def run_card(self, kernel, code, **fields):
        command = kernel.run_card(textwrap.dedent(code), **fields)
        self.done(kernel)
        return command, [line for line in kernel.lines if line["command"] == command.id]

    def run_forms(self, kernel, text, **where):
        command = kernel.run_forms(text, **where)
        self.done(kernel)
        return command, [line for line in kernel.lines if line["command"] == command.id]

    def kinds(self, lines):
        return [(line["kind"], line["text"]) for line in lines]

    def test_opens_fresh_then_warm(self):
        first = self.kernel()
        self.assertEqual(first.start, "fresh")
        self.assertEqual(first.versions["lm"].id, "LUM210")
        self.assertEqual(first.variation, "standard")
        first.close()
        self.done(first)
        second = self.kernel()
        self.assertEqual(second.start, "warm")

    def test_defaults_and_choices(self):
        kernel = self.kernel(versions={"lm": "LUM131"}, variation="extended")
        self.assertEqual(kernel.state()["versions"], {"lm": "LUM131"})
        command, _ = self.run_forms(kernel, "mission")
        self.assertEqual(kernel.lines[-1]["text"], "=> :extended")

    def test_refuses_what_it_cant_do(self):
        with self.assertRaises(KernelError):
            Kernel(self.host, self.root, "T/tc.rst", environment="lms")
        with self.assertRaises(KernelError):
            Kernel(self.host, self.root, "T/tc.rst", variation="nope")
        with self.assertRaises(KernelError):
            Kernel(self.host, self.root, "T/tc.rst", versions={"lm": "LUM999"})

    def test_the_scripts_definitions_and_core_are_loaded(self):
        kernel = self.kernel()
        command, lines = self.run_forms(kernel, "(twice touchdown-vz-limit)")
        self.assertEqual(command.outcome, "pass")
        self.assertEqual(lines[-1], {**lines[-1], "kind": "result", "text": "=> 6.1"})

    def test_a_card_runs_its_steps(self):
        kernel = self.kernel()
        command, lines = self.run_card(kernel, '''
            (boot :standard :surface)
            (Verify (Read landed))
        ''', title="Boot on the surface")
        self.assertEqual(command.outcome, "pass")
        kinds = self.kinds(lines)
        self.assertEqual(kinds[0], ("command", "▶ Boot on the surface"))
        steps = [text for kind, text in kinds if kind == "step"]
        self.assertEqual(steps, ["✓ (boot :standard :surface)", "✓ (Verify (Read landed))"])
        self.assertIn(("out", "landed is true"),
                      [(k, t) for k, t in kinds if k == "out"] or kinds)

    def test_a_failure_says_where_in_the_card(self):
        kernel = self.kernel()
        command, lines = self.run_card(kernel, '''
            (Verify (twice 2) = 4)
            (Verify (twice 2) = 5)
            (Verify true)
        ''')
        self.assertEqual(command.outcome, "fail")
        fail = [line for line in lines if line["kind"] == "fail"][0]
        # The card's code starts with a blank line, which counts
        self.assertEqual(fail["at"], {"line": 2, "character": 0})
        steps = [line["text"] for line in lines if line["kind"] == "step"]
        self.assertEqual(len(steps), 2, "the card stops at the first failure")

    def test_redefining_a_function(self):
        kernel = self.kernel()
        command, lines = self.run_card(kernel, "(defn twice [x] (* 3 x))",
                                       definitions=True)
        self.assertEqual(lines[-1]["text"], "defined twice")
        self.run_forms(kernel, "(twice 2)")
        self.assertEqual(kernel.lines[-1]["text"], "=> 6")

    def test_forms_typed_keep_their_place(self):
        kernel = self.kernel()
        command, lines = self.run_forms(kernel, "(Verify 1 = 2)", line=3, character=4)
        fail = [line for line in lines if line["kind"] == "fail"][0]
        self.assertEqual(fail["at"], {"line": 3, "character": 4})

    def test_printing(self):
        kernel = self.kernel()
        command, lines = self.run_forms(kernel, '(print "ABC")')
        self.assertEqual([(l["kind"], l["text"]) for l in lines[1:]],
                         [("step", '✓ (print "ABC")'), ("printed", "ABC"), ("result", "=> nil")])

    def test_a_definition_typed_is_kept(self):
        kernel = self.kernel()
        self.run_forms(kernel, "(def answer 42)")
        self.assertEqual(kernel.lines[-1]["text"], "=> #'answer")
        self.run_forms(kernel, "(+ answer 1)")
        self.assertEqual(kernel.lines[-1]["text"], "=> 43")

    def test_a_precondition_heals(self):
        kernel = self.kernel()
        command, lines = self.run_card(kernel, '''
            (Precondition "On the surface"
              (lm-ready? :standard :surface)
              :heal "Boot on the surface"
              (boot :standard :surface))
        ''')
        self.assertEqual(command.outcome, "pass")
        phases = [line["text"] for line in lines if line["kind"] == "phase"]
        self.assertEqual(phases, ["check ✗, heal ✓, check ✓"])

    def test_a_precondition_is_named_by_its_description(self):
        kernel = self.kernel()
        command, lines = self.run_card(kernel, '''
            (Precondition "Nothing to do" (= 1 1))
        ''')
        texts = [line["text"] for line in lines]
        self.assertEqual(texts[:2], ["▶ Precondition: Nothing to do",
                                     "✓ Precondition: Nothing to do"])

    def test_a_form_from_a_table_card_gets_the_first_row(self):
        kernel = self.kernel()
        table = '''("x doubled"
  ["one" [1 2]
   "two" [2 4]])

(Verify (twice x) = doubled)'''
        command = kernel.run_forms("(Verify (twice x) = doubled)", line=4, table=table)
        self.done(kernel)
        lines = [line for line in kernel.lines if line["command"] == command.id]
        self.assertEqual(command.outcome, "pass")
        self.assertEqual(lines[1]["text"], "with row one")

    def test_an_unknown_name_has_no_traceback(self):
        kernel = self.kernel()
        command, lines = self.run_forms(kernel, "(Read nowhere)")
        self.assertEqual([line["kind"] for line in lines if line["kind"] == "error"], [])

    def test_a_table_card(self):
        kernel = self.kernel()
        command, lines = self.run_card(kernel, '''
            ("x doubled"
              ["one" [1 2]
               "two" [2 4]
               "three" [3 7]])

            (Verify (twice x) = doubled)
        ''', table=True)
        self.assertEqual(command.outcome, "fail")
        rows = [line["text"] for line in lines if line["kind"] == "row"]
        self.assertEqual(len(rows), 3)

    def test_held_values_stay_until_reset(self):
        kernel = self.kernel()
        self.run_card(kernel, "(boot :standard :surface)")
        self.run_forms(kernel, "(SetFixedValue bench.bus-load-amps 200)")
        self.assertEqual(len(kernel.state()["held"]), 1)
        self.run_forms(kernel, "(Read bench.bus-load-amps)")
        self.assertEqual(kernel.lines[-1]["text"], "=> 200.0")
        kernel.reset()
        self.done(kernel)
        self.assertEqual(kernel.state()["held"], [])
        texts = [line["text"] for line in kernel.lines]
        self.assertIn("released 1 held value", texts)
        self.assertIn("reset", texts)

    def test_release_without_reset(self):
        kernel = self.kernel()
        self.run_forms(kernel, "(def kept 1)")
        self.run_forms(kernel, "(SetFixedValue bench.bus-load-amps 200)")
        kernel.release()
        self.done(kernel)
        self.assertEqual(kernel.state()["held"], [])
        self.run_forms(kernel, "kept")
        self.assertEqual(kernel.lines[-1]["text"], "=> 1", "release keeps the env")

    def test_reset_reloads_the_files(self):
        kernel = self.kernel()
        self.run_forms(kernel, "(def scratch 1)")
        script = self.root / "T" / "tc.rst"
        script.write_text(script.read_text().replace("(* 2 x)", "(* 10 x)"))
        kernel.reset()
        self.done(kernel)
        command, lines = self.run_forms(kernel, "(twice 1)")
        self.assertEqual(lines[-1]["text"], "=> 10")
        command, lines = self.run_forms(kernel, "scratch")
        self.assertEqual(command.outcome, "error", "reset forgets what was typed")

    def test_restart_starts_the_lm_fresh(self):
        kernel = self.kernel()
        self.run_card(kernel, "(boot :standard :surface)")
        kernel.restart()
        self.done(kernel)
        self.assertEqual(kernel.start, "fresh")
        self.run_forms(kernel, "(lm-ready? :standard :pdi)")
        self.assertEqual(kernel.lines[-1]["text"], "=> true")

    def test_stop_ends_a_long_wait(self):
        kernel = self.kernel()
        kernel.run_forms("(Wait (twice 1) = 3 :within 1h)")
        time.sleep(0.3)
        self.assertTrue(kernel.busy())
        kernel.stop()
        self.done(kernel, 10)
        texts = [line["text"] for line in kernel.lines]
        self.assertIn("stopped", texts)
        self.assertFalse([t for t in texts if "Stopped" in t], "the stop isn't a failure")
        self.run_forms(kernel, "(twice 4)")
        self.assertEqual(kernel.lines[-1]["text"], "=> 8", "the kernel goes on")

    def test_a_card_for_another_variation_is_refused(self):
        kernel = self.kernel()
        command, lines = self.run_card(kernel, "(Verify true)", variations=["extended"])
        self.assertEqual(command.outcome, "skipped")
        self.assertIn("extended", lines[-1]["text"])

    def test_attachments_are_kept(self):
        kernel = self.kernel()
        self.run_card(kernel, "(boot :standard :high-gate)")
        command, lines = self.run_card(kernel, '''
            (FlyTo :low-gate)
            (AttachTrajectory "descent")
        ''')
        files = [line for line in lines if line["kind"] == "file"]
        self.assertEqual([f["text"] for f in files], ["descent.csv", "descent.svg"])
        self.assertTrue((self.dir / "files" / files[1]["file"]).is_file())


class FindFormTest(unittest.TestCase):
    CODE = "(boot :standard :pdi)\n(Verify\n  (Read landed))\n"

    def test_the_form_the_cursor_is_in(self):
        self.assertEqual(find_form(self.CODE, 2, 5), ("(Verify\n  (Read landed))", 1, 0))
        self.assertEqual(find_form(self.CODE, 0, 3), ("(boot :standard :pdi)", 0, 0))

    def test_just_after_a_form(self):
        self.assertEqual(find_form(self.CODE, 0, 21), ("(boot :standard :pdi)", 0, 0))

    def test_nothing_before_the_cursor(self):
        self.assertIsNone(find_form("\n\n(a)", 0, 0))


class StopTest(unittest.TestCase):
    def test_a_clock_sleep_stops(self):
        import threading
        event = threading.Event()
        event.set()
        with context.stopping(event), self.assertRaises(context.Stopped):
            clock.WallClock().sleep(5)

    def test_no_stop_without_an_event(self):
        context.check_stopped()


if __name__ == "__main__":
    unittest.main()
