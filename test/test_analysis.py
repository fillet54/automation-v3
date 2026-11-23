"""Static analysis: every name and call checked before a script runs"""

import shutil
import tempfile
import unittest
from pathlib import Path

from automationv3.framework.closure import resolve

from .rvt import doc, rvt

CORE = rvt("""
(uut :lm)
(def limit 80)
(defn check [p] (Verify p <= limit))
(defn two ([a] a) ([a b] (+ a b)))
(defn in-mode? [] (= (.mission lm) mode))
""")


def check(script, core=CORE, files=None):
    root = Path(tempfile.mkdtemp())
    try:
        for path, text in {"core.rst": core, "s.rst": script, **(files or {})}.items():
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(text)
        closure = resolve(root, "s.rst")
        return closure.errors, closure.warnings
    finally:
        shutil.rmtree(root)


class TestNames(unittest.TestCase):
    def test_a_clean_script(self):
        self.assertEqual(check(rvt("(check 70) (Verify (two 1 2) = 3)")), ([], []))

    def test_unknown_name_with_where_and_a_suggestion(self):
        errors, _ = check(rvt("(Verify (+ limt 1) = 81)"))
        (error,) = errors
        self.assertTrue(error.startswith("s.rst:3:15: unknown name limt"), error)
        self.assertIn("did you mean limit?", error)

    def test_unknown_function(self):
        (error,) = check(rvt("(chek 70)"))[0]
        self.assertIn("unknown name chek; did you mean check?", error)

    def test_locals_are_known_in_their_scope_only(self):
        self.assertEqual(check(rvt("(let [x 1 y (+ x 1)] (Verify y = 2))"))[0], [])
        (error,) = check(rvt("(let [x 1] x) (Verify x = 1)"))[0]
        self.assertIn("unknown name x", error)

    def test_handles_are_known(self):
        self.assertEqual(check(rvt("(Verify (.booted lm))"))[0], [])

    def test_used_before_defined(self):
        (error,) = check(rvt("(Verify later = 1) (def later 1)"))[0]
        self.assertIn("later is used before it is defined (line 3)", error)

    def test_a_function_body_may_use_later_definitions(self):
        script = rvt("(defn f [] later) (def later 1) (Verify (f) = 1)")
        self.assertEqual(check(script)[0], [])

    def test_handles_are_not_bound_while_the_definitions_section_loads(self):
        script = doc(rvt("(def m (.mission lm))", "definitions"), rvt("(Wait 1)"))
        (error,) = check(script)[0]
        self.assertIn("lm isn't bound yet here", error)

    def test_core_functions_are_checked_when_the_script_can_call_them(self):
        # in-mode? needs a `mode` variation symbol: fine until it's called
        self.assertEqual(check(rvt("(Wait 1)"))[0], [])
        (error,) = check(rvt("(Verify (in-mode?))"))[0]
        self.assertTrue(error.startswith("core.rst:"), error)
        self.assertIn("unknown name mode (used by in-mode?, which this script calls)",
                      error)
        script = rvt('(variations "mode" ["a" [:normal]]) (Verify (in-mode?))')
        self.assertEqual(check(script)[0], [])

    def test_variation_scoped_definitions(self):
        script = doc(
            rvt('(variations "x" ["a" [1] "b" [2]])'),
            rvt("(def only-a 1)", "definitions", variations="a"),
            rvt("(Verify only-a = 1)"))
        (error,) = check(script)[0]
        self.assertIn("unknown name only-a", error)
        self.assertTrue(error.endswith("(in variation b)"), error)


class TestShapes(unittest.TestCase):
    def test_definitions_only_at_the_top_level(self):
        error, *_ = check(rvt("(defn f [] (def x 1) x)"))[0]
        self.assertIn("def is only allowed at the top level", error)
        (error,) = check(rvt("(if true (defn g [] 1))"))[0]
        self.assertIn("defn is only allowed at the top level", error)

    def test_no_block_calls_while_definitions_load(self):
        script = doc(rvt("(def v (Wait 1))", "definitions"), rvt("(Wait 1)"))
        (error,) = check(script)[0]
        self.assertIn("Wait can't be called here", error)
        self.assertEqual(check(rvt("(def v (Wait 1)) (defn f [] (Wait 1))"))[0], [])

    def test_arity(self):
        (error,) = check(rvt("(check 1 2)"))[0]
        self.assertIn("check takes 1 argument, not 2 (defined in core.rst:5)", error)
        (error,) = check(rvt("(two)"))[0]
        self.assertIn("two takes 1 or 2 arguments, not 0", error)

    def test_rest_arity(self):
        core = CORE + rvt("(defn log [fmt & args] fmt) (defn many ([] 0) ([a b & r] a))")
        self.assertEqual(check(rvt("(log 1) (log 1 2 3) (many) (many 1 2 3)"), core)[0], [])
        (error,) = check(rvt("(log)"), core)[0]
        self.assertIn("log takes 1 or more arguments, not 0", error)
        (error,) = check(rvt("(many 1)"), core)[0]
        self.assertIn("many takes 0, or 2 or more arguments, not 1", error)

    def test_destructured_names_are_bound(self):
        script = rvt("(let [{:keys [a] [b & c] :v :or {a limit} :as m} {} [d] [1]] "
                     "(Verify (+ a b d (count c) (count m)) = 1)) "
                     "(defn f [[x] & {:keys [y]}] (+ x y))")
        self.assertEqual(check(script)[0], [])
        (error,) = check(rvt("(let [{:keys [a] :or {a limt}} {}] a)"))[0]
        self.assertIn("unknown name limt", error)

    def test_a_named_fn_may_call_itself(self):
        script = rvt("(def fact (fn f [n] (if (< n 2) 1 (* n (f (- n 1)))))) (Verify (fact 3) = 6)")
        self.assertEqual(check(script)[0], [])
        (error,) = check(rvt("(def g (fn f [n] n)) (Verify (f 1) = 1)"))[0]
        self.assertIn("unknown name f", error)  # only inside it

    def test_bad_patterns(self):
        for script, message in [
                ("(let [1 2] 1)", "can only bind names"),
                ("(let [[a & b c] [1]] a)", "only :as can follow & rest"),
                ("(let [{:keys [a] :or {z 1}} {}] a)", ":or gives a default for z"),
                ("(defn f [a :as b] a)", "parameters can't use :as"),
                ("(defn f ([& a] 1) ([& b] 2))", "only one arity with & rest"),
                ("(defn f ([a b] 1) ([& b] 2))", "fixed arity taking more arguments"),
                ("(defn f ([a] 1) ([b] 2))", "two arities taking 1 argument")]:
            with self.subTest(script):
                errors = check(rvt(script))[0]
                self.assertTrue(any(message in e for e in errors), errors)

    def test_builtin_arity(self):
        (error,) = check(rvt("(Verify (not 1 2))"))[0]
        self.assertIn("not can't take 2 arguments", error)
        self.assertEqual(check(rvt("(Verify (= (- 3) (- 1 2 2)))"))[0], [])

    def test_block_syntax(self):
        (error,) = check(rvt("(Verify 1 2 3)"))[0]
        self.assertIn("no form of Verify matches this call: see its usage, "
                      "(Verify actual predicate args...) or (Verify value)", error)

    def test_a_check_names_its_predicate(self):
        (error,) = check(rvt("(Verify 1 ~ 2)"))[0]
        self.assertIn("unknown name ~", error)
        self.assertEqual(check(rvt("(defn within? [v lo hi] (and (>= v lo) (<= v hi)))\n"
                                   "(Verify 2 within? 1 3)"))[0], [])

    def test_quoted_and_as_written_arguments_are_not_names(self):
        self.assertEqual(check(rvt("(Verify 1 <= 2) (Keys \"V16N68E\") (FlyTo :high-gate :within 600)"))[0],
                         [])

    def test_special_form_shapes(self):
        self.assertIn("step takes a title", check(rvt("(step (Wait 1))"))[0][0])
        self.assertIn("try takes a form and a default", check(rvt("(try (Wait 1))"))[0][0])
        self.assertIn("if takes a test", check(rvt("(if true)"))[0][0])


class TestWarnings(unittest.TestCase):
    def test_a_discarded_value(self):
        errors, (warning,) = check(rvt("(- 10 10)"))
        self.assertEqual(errors, [])
        self.assertIn("the value of (- 10 10) is not used", warning)
        self.assertIn("Did you mean (Verify ...)?", warning)

    def test_function_calls_are_not_discarded(self):
        self.assertEqual(check(rvt("(check 1) (two 1) (print 1) (println 1)"))[1], [])

    def test_shadowing(self):
        _, (warning,) = check(rvt("(def Wait 1)"))
        self.assertIn("Wait shadows the block Wait", warning)
        _, (warning,) = check(rvt("(def limit 10)"))
        self.assertIn("limit shadows the definition in core.rst:4", warning)


if __name__ == "__main__":
    unittest.main()
