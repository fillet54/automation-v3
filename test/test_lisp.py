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

    def test_a_named_fn_can_call_itself(self):
        self.assertEqual(run("((fn fact [n] (if (< n 2) 1 (* n (fact (- n 1))))) 5)"), 120)
        with self.assertRaises(lisp.UnboundName):
            run("(fn fact [n] n) (fact 1)")  # the name is the fn's own, not bound outside

    def test_rest_parameters(self):
        self.assertEqual(run("((fn [x & more] [x more]) 1 2 3)"), [1, [2, 3]])
        self.assertEqual(run("((fn [x & more] more) 1)"), [])  # empty, not nil
        self.assertEqual(run("(defn f ([] :none) ([x] :one) ([x & r] (count r))) [(f) (f 1) (f 1 2 3)]"),
                         [edn.Keyword("none"), edn.Keyword("one"), 2])
        with self.assertRaises(RuntimeError):
            run("((fn [a b & r] a) 1)")
        for bad in ["(fn ([& a] 1) ([& b] 2))", "(fn ([a b c] 1) ([& b] 2))",
                    "(fn ([a] 1) ([b] 2))", "(fn [a &] a)", "(fn [a :as b] a)"]:
            with self.subTest(bad), self.assertRaises(ValueError):
                run(bad)

    def test_sequence_destructuring(self):
        self.assertEqual(run("(let [[a [b c] & r :as all] [1 [2 3] 4 5]] [a b c r all])"),
                         [1, 2, 3, [4, 5], [1, [2, 3], 4, 5]])
        self.assertEqual(run("(let [[a b] [1]] [a b])"), [1, None])
        self.assertEqual(run("(let [[a b] nil] [a b])"), [None, None])
        self.assertEqual(run("((fn [[x y] z] [x y z]) [1 2] 3)"), [1, 2, 3])
        with self.assertRaises(ValueError):
            run("(let [[a & b c] [1]] a)")

    def test_map_destructuring(self):
        self.assertEqual(run('(let [{a :a {x :x} :inner [p q] :pos} '
                             '{:a 1 :inner {:x 2} :pos [3 4]}] [a x p q])'), [1, 2, 3, 4])
        self.assertEqual(run('(let [{:keys [a b] :strs [c] :syms [d] :as m} {:a 1 "b" 2 :c 3 :d 4}] '
                             '[a b c d (count m)])'), [1, 2, 3, 4, 4])
        self.assertEqual(run("(let [{[p q] :pos} {:pos [1 2]}] (+ p q))"), 3)
        self.assertEqual(run("(let [{:keys [a]} nil] a)"), None)

    def test_or_defaults_apply_to_missing_keys_only(self):
        self.assertEqual(run("(let [d 5 {:keys [a b] :or {a d b 2}} {:b nil}] [a b])"), [5, None])
        with self.assertRaises(ValueError):
            run("(let [{:keys [a] :or {z 1}} {}] a)")

    def test_keyword_arguments(self):
        self.assertEqual(run("(defn f [x & {:keys [scale] :or {scale 1}}] (* x scale)) "
                             "[(f 2) (f 2 :scale 3)]"), [2, 6])

    def test_let_binds_only_patterns(self):
        with self.assertRaises(ValueError):
            run("(let [1 2] 1)")
        with self.assertRaises(ValueError):
            run("(let [a] 1)")

    def test_vectors_maps_and_sets_evaluate_their_items(self):
        self.assertEqual(run("[(+ 1 2) :k]"), [3, edn.Keyword("k")])
        self.assertEqual(run("(def x 2) {:a x}"), {edn.Keyword("a"): 2})
        self.assertEqual(run("#{(+ 1 1)}"), {2})
        self.assertIsInstance(run("[1]"), edn.Vector)

    def test_arithmetic_takes_any_number_of_arguments(self):
        self.assertEqual(run("(list (+) (+ 1 2 3) (- 5) (- 10 1 2) (* 2 3 4) (/ 8 2 2))"),
                         [0, 6, -5, 7, 24, 2.0])
        self.assertEqual(run('(+ "a" "b")'), "ab")

    def test_quote_keeps_data_as_written(self):
        self.assertEqual(run("'[(+ 1 2)]"), [["+", 1, 2]])

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


class TestEnvSnapshot(unittest.TestCase):
    def test_local_items_while_another_thread_binds(self):
        import threading
        env, done, errors = lisp.Env(), threading.Event(), []

        def bind():
            n = 0
            while not done.is_set():
                env[edn.Symbol(f"x{n}")] = n
                env.pop(edn.Symbol(f"x{n - 50}"), None)
                n += 1

        thread = threading.Thread(target=bind)
        thread.start()
        try:
            for _ in range(2000):
                try:
                    env.local_items()
                except RuntimeError as e:
                    errors.append(e)
        finally:
            done.set()
            thread.join()
        self.assertEqual(errors, [])
