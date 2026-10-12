"""Default collection helpers over EDN values and iterator-producing builtins."""

import unittest

from automationv3.framework import edn
from automationv3.framework.lisp_helpers import nth
from .test_lisp import run
from .test_analysis import check
from .rvt import rvt


class TestLispHelpers(unittest.TestCase):
    def test_get_preserves_false_and_nil_and_uses_defaults_only_when_missing(self):
        self.assertEqual(run('(vector (get {:a false} :a true) '
                             '(get {:a nil} :a 7) (get {} :a 7) (get nil :a 7))'),
                         [False, None, 7, 7])
        self.assertEqual(run('(vector (get [10 20] 1) (get [10] -1 :missing) '
                             '(get [10] true :missing) (get "abc" 1))'),
                         [20, edn.Keyword("missing"), edn.Keyword("missing"), "b"])

    def test_get_in_traverses_maps_and_vectors(self):
        self.assertEqual(run('(get-in {:a [{:b false}]} [:a 0 :b] :missing)'), False)
        self.assertIsNone(run('(get-in {:a nil} [:a] 3)'))
        self.assertEqual(run('(get-in {:a nil} [:a :b] 3)'), 3)
        self.assertEqual(run('(get-in {:a 1} [] 3)'), {edn.Keyword("a"): 1})

    def test_nth_accepts_iterators_and_handles_missing_indexes(self):
        self.assertEqual(run('(nth (map (fn [x] (* x 2)) [1 2 3]) 1)'), 4)
        self.assertIsNone(run('(nth [] 2 nil)'))
        self.assertEqual(run('(nth [1] -1 :missing)'), edn.Keyword("missing"))
        with self.assertRaises(IndexError):
            run('(nth [1] 2)')
        with self.assertRaises(TypeError):
            run('(nth [1] true)')
        self.assertEqual(nth(iter([2, 4]), 1), 4)

    def test_contains_checks_keys_or_indexes_not_sequence_values(self):
        self.assertEqual(run('(vector (contains? {:a nil} :a) (contains? #{:a} :a) '
                             '(contains? [10 20] 1) (contains? [10 20] 20) '
                             '(contains? [10] -1) (contains? nil :a))'),
                         [True, True, True, False, False, False])

    def test_keys_and_vals_are_reusable_vectors_in_insertion_order(self):
        result = run('(vector (keys {:b 2 :a 1}) (vals {:b 2 :a 1}))')
        self.assertEqual(result, [[edn.Keyword("b"), edn.Keyword("a")], [2, 1]])
        self.assertTrue(all(isinstance(item, edn.Vector) for item in result))
        self.assertEqual(run('(count (keys nil))'), 0)

    def test_vector_and_vec_materialize_values_without_mutating_input(self):
        self.assertEqual(run('(vec (map (fn [x] (+ x 1)) [1 2]))'), [2, 3])
        self.assertIsInstance(run('(vector 1 2)'), edn.Vector)
        self.assertEqual(run('(vec nil)'), [])
        self.assertEqual(run('(def a [1 2]) (def b (vec a)) (assoc b 0 3) a'), [1, 2])

    def test_filter_evaluates_a_script_predicate_and_returns_a_vector(self):
        result = run('(defn large? [x] (> x 2)) (filter large? [1 2 3 4])')
        self.assertEqual(result, [3, 4])
        self.assertIsInstance(result, edn.Vector)
        self.assertEqual(run('(filter nil nil)'), [])

    def test_reduce_supports_both_arities_and_empty_collections(self):
        self.assertEqual(run('(vector (reduce + [1 2 3]) (reduce + 10 [1 2 3]) '
                             '(reduce + []) (reduce + 10 []) (reduce + nil))'),
                         [6, 16, 0, 10, 0])
        self.assertEqual(run('(reduce (fn [a x] (assoc a x (* x x))) {} [1 2])'),
                         {1: 1, 2: 4})

    def test_wrong_collection_types_and_argument_counts_are_reported(self):
        for expression in ['(get 3 :a)', '(keys [1])', '(vals [1])', '(nth {:a 1} 0)']:
            with self.subTest(expression=expression), self.assertRaises(TypeError):
                run(expression)
        for expression in ['(get {})', '(get-in)', '(nth [])', '(reduce +)', '(filter +)']:
            with self.subTest(expression=expression):
                self.assertTrue(check(rvt('(Verify ' + expression + ')'), core='')[0])

    def test_get_takes_set_members(self):
        self.assertEqual(run('(vector (get #{1 2} 1) (get #{1 2} 3) (get #{1 2} 3 :missing))'),
                         [1, None, edn.Keyword("missing")])

    def test_sequence_functions_are_eager_vectors(self):
        for expression, expected in [('(map (fn [x] (* x 2)) [1 2 3])', [2, 4, 6]),
                                     ('(map + [1 2 3] [10 20])', [11, 22]),
                                     ('(take 2 [1 2 3])', [1, 2]),
                                     ('(take 5 [1 2])', [1, 2]),
                                     ('(take 3 (cycle [1 2]))', [1, 2, 1]),
                                     ('(rest [1 2 3])', [2, 3]),
                                     ('(rest [])', []),
                                     ('(cons 0 [1 2])', [0, 1, 2]),
                                     ('(partition 2 [1 2 3 4 5])', [[1, 2], [3, 4]]),
                                     ('(map (fn [x] x) nil)', [])]:
            with self.subTest(expression=expression):
                result = run(expression)
                self.assertEqual(result, expected)
                self.assertIsInstance(result, edn.Vector)
        self.assertEqual(run('(def xs (map (fn [x] x) [1 2])) (vector (count xs) (count xs))'),
                         [2, 2])
