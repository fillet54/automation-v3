"""framework/source.py: a script as one docutils tree"""

import unittest

from docutils import nodes

from automationv3.framework import edn, source
from automationv3.framework.source import rvt_block, rvt_variant

SCRIPT = """\
================
Brake Monitoring
================
Checks the brake pressure stays under the limit.

Requirements
------------
1. :req:`VMCBRA00001` and :req:`VMCBRA00002`

.. rvt::
   :definitions:

   (def target 60)

Steps
-----
Apply the brakes, see :req:`VMCBRA00003`.

.. rvt:: Apply the brakes
   fully
   :variations: degraded, limp-home

   (set-reading :brake-pressure
                target)
   (Verify 1 = 1)

.. rvt-variant::
   :variations: emergency

   In emergency mode.

   .. rvt::

      (Verify 2 = 2)

Notes
~~~~~
Done.
"""


def text_at(text, span):
    """The text a one-line span covers"""
    return text.splitlines()[span.line - 1][span.col:span.end_col]


def form_text(text, span):
    lines = text.splitlines()[span.line - 1:span.end_line]
    if len(lines) == 1:
        return lines[0][span.col:span.end_col]
    return "\n".join([lines[0][span.col:]] + lines[1:-1] + [lines[-1][:span.end_col]])


class Tree(unittest.TestCase):

    def setUp(self):
        self.tree = source.parse(SCRIPT, "BRA/tc.rst")

    def test_the_tree_is_shaped_like_the_file(self):
        top = self.tree.children[0]
        self.assertIsInstance(top, nodes.section)  # no doctitle transform
        sections = [s[0].astext() for s in self.tree.findall(nodes.section)]
        self.assertEqual(sections, ["Brake Monitoring", "Requirements", "Steps", "Notes"])
        steps = list(self.tree.findall(nodes.section))[2]
        self.assertEqual([type(b) for b in source.blocks(steps)], [rvt_block, rvt_variant])

    def test_blocks_and_walk(self):
        found = source.blocks(self.tree)
        self.assertEqual([type(b) for b in found], [rvt_block, rvt_block, rvt_variant])
        self.assertEqual([type(b) for b in source.blocks(found[2])], [rvt_block])
        self.assertEqual(len(list(source.walk(self.tree))), 4)

    def test_block_lines(self):
        definitions, steps, variant = source.blocks(self.tree)
        inner = source.blocks(variant)[0]
        self.assertEqual((definitions["line"], definitions["end"]), (10, 13))
        self.assertEqual((steps["line"], steps["end"]), (19, 25))
        self.assertEqual((variant["line"], variant["end"]), (27, 34))
        self.assertEqual((inner["line"], inner["end"]), (32, 34))
        self.assertEqual([b["content_line"] for b in (definitions, steps, inner)], [13, 23, 34])
        self.assertEqual([b["indent"] for b in (definitions, steps, variant, inner)], [3, 3, 3, 6])

    def test_block_fields(self):
        definitions, steps, variant = source.blocks(self.tree)
        inner = source.blocks(variant)[0]
        self.assertEqual(definitions["options"], {"definitions": ""})
        self.assertIsNone(definitions["title"])
        self.assertEqual(steps["title"], "Apply the brakes fully")
        self.assertEqual(steps["options"], {"variations": ["degraded", "limp-home"]})
        self.assertEqual(steps["variations"], ["degraded", "limp-home"])
        self.assertEqual(variant["variations"], ["emergency"])
        self.assertEqual(inner["options"], {})
        self.assertEqual(inner["variations"], ["emergency"])  # its variant's
        self.assertEqual(steps["code"],
                         "(set-reading :brake-pressure\n             target)\n(Verify 1 = 1)")
        self.assertEqual(source.problems(self.tree), [])

    def test_form_spans_are_in_the_file(self):
        for block in source.walk(self.tree):
            if isinstance(block, rvt_block):
                for form, span in block["forms"]:
                    self.assertEqual(span.source, "BRA/tc.rst")
                    self.assertEqual(edn.read(form_text(SCRIPT, span)), form)
        steps = source.blocks(self.tree)[1]
        first, _ = steps["forms"][0]
        self.assertEqual(edn.span_of(first)[:4], (23, 3, 24, 23))
        target = edn.item_span(first, 2)
        self.assertEqual(text_at(SCRIPT, target), "target")
        inner = source.blocks(source.blocks(self.tree)[2])[0]
        self.assertEqual(inner["forms"][0][1][:4], (34, 6, 34, 20))

    def test_title(self):
        self.assertEqual(source.title(self.tree), "Brake Monitoring")
        self.assertIsNone(source.title(source.parse("Just text.\n")))

    def test_titles_are_located(self):
        found = [(t.astext(), source.locate(self.tree, t)[:4])
                 for t in self.tree.findall(nodes.title)]
        self.assertEqual(found, [("Brake Monitoring", (2, 0, 2, 16)),
                                 ("Requirements", (6, 0, 6, 12)),
                                 ("Steps", (15, 0, 15, 5)),
                                 ("Notes", (36, 0, 36, 5))])

    def test_requirement_refs_are_located(self):
        found = source.requirement_refs(self.tree)
        self.assertEqual([id for id, _ in found], ["VMCBRA00001", "VMCBRA00002", "VMCBRA00003"])
        for id, span in found:
            self.assertEqual(text_at(SCRIPT, span), f":req:`{id}`")
            self.assertEqual(span.source, "BRA/tc.rst")

    def test_cached_by_text_and_path(self):
        self.assertIs(source.parse(SCRIPT, "BRA/tc.rst"), self.tree)
        self.assertIsNot(source.parse(SCRIPT, "other.rst"), self.tree)


class Variants(unittest.TestCase):

    def test_title_inside_a_variant_is_located(self):
        # "~" is the style of Notes, a level below Steps, which the variant is in
        text = SCRIPT.replace("   In emergency mode.\n", "   Emergency\n   ~~~~~~~~~\n\n   In emergency mode.\n")
        tree = source.parse(text)
        self.assertEqual(source.problems(tree), [])
        notes = [s for s in tree.findall(nodes.section) if s[0].astext() == "Notes"][0]
        self.assertEqual(notes.parent[0].astext(), "Steps")  # still under Steps
        title = [t for t in tree.findall(nodes.title) if t.astext() == "Emergency"][0]
        self.assertIsNone(title.line)
        self.assertEqual(source.locate(tree, title)[:4], (30, 3, 30, 12))

    def test_heading_at_an_enclosing_level_is_a_problem(self):
        text = SCRIPT.replace("   In emergency mode.\n", "   Emergency\n   ---------\n\n   In emergency mode.\n")
        (problem,) = source.problems(source.parse(text))
        self.assertIn("section cannot be used here", problem.message)

    def test_three_levels(self):
        text = """\
.. rvt-variant::
   :variations: a, b, c

   .. rvt-variant::
      :variations: a, b

      .. rvt-variant::
         :variations: a

         .. rvt::

            (Verify
               1 = 1)
"""
        tree = source.parse(text)
        self.assertEqual(source.problems(tree), [])
        blocks = list(source.walk(tree))
        self.assertEqual([b["variations"] for b in blocks], [["a", "b", "c"], ["a", "b"], ["a"], ["a"]])
        self.assertEqual([b["indent"] for b in blocks], [3, 6, 9, 12])
        form, span = blocks[3]["forms"][0]
        self.assertEqual(span[:4], (12, 12, 13, 21))
        self.assertEqual(form_text(text, span), "(Verify\n               1 = 1)")
        self.assertEqual(text_at(text, edn.item_span(form, 1)), "1")
        self.assertEqual(edn.item_span(form, 1)[:2], (13, 15))

    def test_variations_outside_the_variant(self):
        text = """\
.. rvt-variant::
   :variations: a

   .. rvt::
      :variations: a, b

      (Wait 1)

   .. rvt-variant::
      :variations: c
"""
        found = source.problems(source.parse(text))
        self.assertEqual([(p.message, p.span.line) for p in found],
                         [("b is outside its rvt-variant (a)", 5),
                          ("c is outside its rvt-variant (a)", 10)])

    def test_variant_without_variations(self):
        tree = source.parse("Text.\n\n.. rvt-variant::\n\n   .. rvt::\n\n      (Wait 1)\n")
        (problem,) = source.problems(tree)
        self.assertEqual(problem.message, "rvt-variant needs a :variations: option")
        self.assertEqual(problem.span[:4], (3, 0, 3, 16))
        variant = source.blocks(tree)[0]
        self.assertEqual(variant["variations"], [])
        self.assertEqual(len(source.blocks(variant)), 1)  # still read


class Problems(unittest.TestCase):

    def test_wrong_options_keep_the_block(self):
        text = "Text.\n\n.. rvt:: Step\n   :defs:\n   :table: yes\n   :variations: a,,b\n\n   (Wait 1)\n"
        tree = source.parse(text, "x.rst")
        [block] = source.blocks(tree)
        self.assertEqual((block["line"], block["end"], block["title"]), (3, 8, "Step"))
        self.assertEqual(len(block["forms"]), 1)
        self.assertEqual(block["options"], {})
        self.assertEqual([(p.message, p.span[:4]) for p in source.problems(tree)], [
            ('unknown option: "defs"', (4, 3, 4, 9)),
            (":table: takes no value", (5, 3, 5, 14)),
            (":variations: expected variation names separated by commas", (6, 3, 6, 20)),
        ])

    def test_code_that_stops_reading(self):
        text = "Text.\n\n.. rvt::\n\n   (Wait 1)\n   (Verify (double\n"
        tree = source.parse(text)
        [block] = source.blocks(tree)
        self.assertEqual([edn.writes(f) for f, _ in block["forms"]], ["(Wait 1)"])
        self.assertIn("Missing closing ')'", block["error"].message)
        self.assertEqual(block["problems"], [])
        (problem,) = source.problems(tree)
        self.assertIs(problem, block["error"])
        self.assertEqual(problem.span.line, 6)

    def test_crlf(self):
        tree = source.parse(SCRIPT.replace("\n", "\r\n"), "BRA/tc.rst")
        self.assertEqual(source.problems(tree), [])
        expected = source.parse(SCRIPT, "BRA/tc.rst")
        spans = [[s for _, s in b["forms"]] for b in source.walk(tree) if "forms" in b]
        self.assertEqual(spans, [[s for _, s in b["forms"]] for b in source.walk(expected)
                                 if "forms" in b])
        self.assertEqual([source.locate(tree, t) for t in tree.findall(nodes.title)],
                         [source.locate(expected, t) for t in expected.findall(nodes.title)])

    def test_a_file_that_is_not_a_script(self):
        text = """\
Guide
=====

.. toctree::
   :maxdepth: 2

See :doc:`intro` and :ref:`there`.

.. code-block:: rst

   .. rvt::

      (Wait 1)
"""
        tree = source.parse(text)
        self.assertEqual(source.problems(tree), [])
        self.assertEqual(source.blocks(tree), [])

    def test_a_directive_swallowed_by_a_paragraph(self):
        tree = source.parse("Title\n=====\nBody.\n.. rvt::\n\n   (Wait 1)\n")
        self.assertEqual(source.statements(tree), [])
        (problem,) = source.unreadable(tree)
        self.assertIn("needs a blank line before it", problem.message)
        self.assertEqual(problem.span[:4], (4, 0, 4, 8))

    def test_a_directive_in_a_literal_block_is_text(self):
        tree = source.parse("Doc\n===\n\n::\n\n   Body.\n   .. rvt::\n\n      (a)\n")
        self.assertEqual(source.unreadable(tree), [])

    def test_docutils_errors_are_problems(self):
        text = "A\n===\n\nB\n---\n\nC\n~~~\n\nD\n===\n\nE\n~~~\n"
        (problem,) = source.problems(source.parse(text))
        self.assertIn("Inconsistent title style", problem.message)
        self.assertEqual(problem.span.line, 13)  # the title, not its underline

    def test_never_raises(self):
        for text in ("", "\n\n", ".. rvt::", ".. rvt-variant::", "   .. rvt::\n  x",
                     ".. rvt:: \\", "====\n", ".. rvt::\n\n   (\"unterminated\n"):
            with self.subTest(text=text):
                source.parse(text)
                source.problems(source.parse(text))


if __name__ == "__main__":
    unittest.main()
