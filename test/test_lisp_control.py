"""Short-circuit logic and bounded ranges, including block execution/reporting."""

import unittest

from automationv3.framework import edn, lisp
from automationv3.framework.plugins import PluginRegistry
from .test_lisp import run
from .test_compose import run as run_test
from .test_analysis import check
from .rvt import rvt


class TestLogic(unittest.TestCase):
    def test_logic_skips_errors_after_the_result_is_decided(self):
        self.assertIs(run('(and false (/ 1 0))'), False)
        self.assertIs(run('(or true (/ 1 0))'), True)
        with self.assertRaises(ZeroDivisionError):
            run('(and true (/ 1 0))')
        with self.assertRaises(ZeroDivisionError):
            run('(or false (/ 1 0))')

    def test_logic_returns_the_deciding_value_and_handles_empty_forms(self):
        self.assertEqual(run('(and 7 9)'), 9)
        self.assertEqual(run('(or nil :fallback (/ 1 0))'), edn.Keyword('fallback'))
        self.assertEqual(run('(and 7 0 (/ 1 0))'), 0)
        self.assertIs(run('(and)'), True)
        self.assertIsNone(run('(or)'))
        self.assertIsNone(run('(and nil true)'))
        self.assertIs(run('(or false false)'), False)

    def test_each_reached_argument_runs_once_in_order(self):
        calls = []
        def touch(value):
            calls.append(value)
            return value
        env = lisp.Env(outer=lisp.global_env)
        env['touch'] = touch
        self.assertEqual(run('(and (touch 1) (touch 0) (touch 3))', env), 0)
        self.assertEqual(calls, [1, 0])
        calls.clear()
        self.assertEqual(run('(or (touch 0) (touch 2) (touch 3))', env), 2)
        self.assertEqual(calls, [0, 2])

    def test_skipped_blocks_produce_no_calls_or_failures(self):
        outcome, rec = run_test('(Verify (or true (Broken))) '
                                '(Verify (not (and false (Refuses))))', core='')
        self.assertEqual(outcome, 'pass')
        self.assertEqual(len(rec.of('step_end')), 2)
        self.assertEqual(rec.of('call_start'), [])

    def test_reached_block_failures_still_stop_the_test(self):
        outcome, rec = run_test('(and true (Refuses)) (Verify true)', core='')
        self.assertEqual(outcome, 'fail')
        self.assertEqual(len(rec.of('step_end')), 1)
        self.assertFalse(rec.of('call_end')[0]['passed'])

    def test_static_analysis_checks_all_branches_even_when_runtime_would_skip_them(self):
        self.assertEqual(check(rvt('(Verify (or false true))'), core='')[0], [])
        errors, _ = check(rvt('(Verify (or true (missing)))'), core='')
        self.assertIn('unknown name missing', ' '.join(errors))

    def test_plugins_cannot_register_functions_named_after_logic_forms(self):
        for name in ['and', 'or']:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'conflicts'):
                PluginRegistry('test.logic').function(name, lambda: True)


class TestRange(unittest.TestCase):
    def test_range_arities_bounds_and_negative_steps(self):
        for expression, expected in [('(range 5)', [0, 1, 2, 3, 4]),
                                     ('(range 2 5)', [2, 3, 4]),
                                     ('(range 2 8 2)', [2, 4, 6]),
                                     ('(range 5 0 -2)', [5, 3, 1]),
                                     ('(range 0)', []), ('(range 3 3)', []),
                                     ('(range 3 0)', [])]:
            with self.subTest(expression=expression):
                actual = run(expression)
                self.assertEqual(actual, expected)
                self.assertIsInstance(actual, edn.Vector)

    def test_invalid_ranges_fail_and_bad_arities_are_caught_statically(self):
        for expression in ['(range)', '(range 1 2 3 4)', '(range 3.5)',
                           '(range true)', '(range 2 nil)']:
            with self.subTest(expression=expression), self.assertRaises(TypeError):
                run(expression)
        with self.assertRaises(ValueError):
            run('(range 0 5 0)')
        for expression in ['(range)', '(range 1 2 3 4)']:
            self.assertIn("range can't take", ' '.join(check(rvt('(Verify ' + expression + ')'), core='')[0]))

    def test_range_integrates_with_count_map_take_reduce_and_edn_reports(self):
        self.assertEqual(run('(count (range 10))'), 10)
        self.assertEqual(run('(reduce + (range 5))'), 10)
        self.assertEqual(run('(vec (map (fn [x] (* x 2)) (range 3)))'), [0, 2, 4])
        self.assertEqual(run('(vec (take 2 (range 5)))'), [0, 1])
        self.assertEqual(edn.writes(run('(range 3)')), '[0 1 2]')
