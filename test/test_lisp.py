"""The script Lisp"""

import unittest

from automationv3.framework import edn, lisp


def run(text, env=None):
    env = env if env is not None else lisp.Env(outer=lisp.global_env)
    value = None
    for form in edn.read_all(text):
        value = lisp.eval(form, env)
    return value


class Thing:
    size = 3

    def double(self, x):
        return 2 * x


class TestLisp(unittest.TestCase):
    def test_literals_and_keywords_evaluate_to_themselves(self):
        self.assertEqual(run('"a"'), "a")
        self.assertEqual(run(":k"), edn.Keyword("k"))
        self.assertEqual(run("()"), [])

    def test_if_do_def_let(self):
        self.assertEqual(run("(if (> 2 1) :yes :no)"), edn.Keyword("yes"))
        self.assertIsNone(run("(if false 1)"))
        self.assertEqual(run("(def x 2) (do 1 (* x 3))"), 6)
        self.assertEqual(run("(let [a 1 b (+ a 1)] (* a b))"), 2)

    def test_fn_and_defn_with_arities(self):
        self.assertEqual(run("(defn f ([x] x) ([x y] (+ x y))) (list (f 1) (f 1 2))"), [1, 3])
        self.assertEqual(run("((fn [x] (* x x)) 4)"), 16)
        with self.assertRaises(RuntimeError):
            run("((fn [x] x))")
        with self.assertRaises(ValueError):
            run("(fn x y)")

    def test_vectors_are_not_evaluated(self):
        # Block arguments are evaluated by context.evaluate, which does
        # look inside vectors and maps; plain Lisp leaves them as written
        self.assertEqual(run("[(+ 1 2)]"), [["+", 1, 2]])

    def test_quote(self):
        self.assertEqual(run("'(a b)"), ["a", "b"])

    def test_dot_calls_methods_and_reads_attributes(self):
        env = lisp.Env([edn.Symbol("t")], [Thing()], outer=lisp.global_env)
        self.assertEqual(run("(.double t 4)", env), 8)
        self.assertEqual(run("(.-size t)", env), 3)

    def test_unbound_symbols(self):
        with self.assertRaises(KeyError) as c:
            run("(missing 1)")
        self.assertIn("missing not found", str(c.exception))

    def test_assoc_leaves_the_original(self):
        env = lisp.Env(outer=lisp.global_env)
        run("(def m {:a 1}) (def n (assoc m :b 2))", env)
        self.assertEqual(len(env[edn.Symbol("m")]), 1)
        self.assertEqual(len(env[edn.Symbol("n")]), 2)
