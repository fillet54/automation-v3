"""Source spans: every form knows where it was written"""

import unittest

from automationv3.framework import document, edn

SCRIPT = """\
Title
=====

.. rvt::
   :definitions:

   (def limit 80)

.. rvt-variant::
   :variations: high

   Prose.

   .. rvt:: Titled

      (Verify (reading :x)
              <= limit)
"""


def text_at(text, span):
    lines = text.splitlines()
    if span.line == span.end_line:
        return lines[span.line - 1][span.col:span.end_col]
    return lines[span.line - 1][span.col:]


class TestReader(unittest.TestCase):
    def test_collections_and_symbols_carry_spans(self):
        (form,) = edn.read_all("(f\n  [x 1] {:a \"s\"})")
        self.assertEqual(edn.span_of(form), edn.Span(0, 0, 1, 17))
        self.assertEqual(edn.span_of(form[0]), edn.Span(0, 1, 0, 2))
        vector = form[1]
        self.assertEqual(edn.span_of(vector), edn.Span(1, 2, 1, 7))
        self.assertEqual(edn.item_span(vector, 1), edn.Span(1, 5, 1, 6))
        key_span, value_span = edn.item_span(form[2], edn.Keyword("a"))
        self.assertEqual(value_span, edn.Span(1, 12, 1, 15))

    def test_numbers_and_strings_are_found_through_their_parent(self):
        (form,) = edn.read_all("(+ 1 2)")
        self.assertIsNone(edn.span_of(form[1]))
        self.assertEqual(edn.item_span(form, 2), edn.Span(0, 5, 0, 6))

    def test_spans_do_not_change_equality(self):
        self.assertEqual(edn.read("(a [b])"), edn.read("(a   [b])"))


class TestDocument(unittest.TestCase):
    def test_spans_are_file_positions(self):
        parts = [p for p in document.parse(SCRIPT, path="s.rst") if not p.prose]
        definition, verify = parts
        self.assertEqual(text_at(SCRIPT, definition.span), "(def limit 80)")
        self.assertEqual(definition.span.source, "s.rst")
        self.assertEqual(definition.span.line, 7)

    def test_spans_inside_variants_account_for_their_indent(self):
        verify = [p for p in document.parse(SCRIPT, path="s.rst") if not p.prose][1]
        self.assertEqual(verify.span.line, 16)
        self.assertEqual(text_at(SCRIPT, edn.span_of(verify.form[1])), "(reading :x)")
        limit = edn.span_of(verify.form[3])
        self.assertEqual((limit.line, text_at(SCRIPT, limit)), (17, "limit"))


if __name__ == "__main__":
    unittest.main()
