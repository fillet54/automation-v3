"""Requirements written in reStructuredText"""

import unittest

from automationv3.documents.html import requirement_html
from automationv3.framework.requirement import Requirement
from automationv3.services.requirements.rst_source import RequirementsError, parse, plain_text

DOCUMENT = """
Power
=====

Prose is ignored.

.. requirement:: LM-EPS-002

   The EPS shall light a light below:

   - 26.5 V: the BATTERY caution;
   - 24 V: the WARNING light.

.. requirement:: SYS-1
   :subsystem: SYSTEM
   :satisfies: TOP-2, TOP-1
   :Last-Modified-By: someone   else

   The platform shall *survive*.

.. requirement:: R-1

   Plain shall be.
"""


class TestParsing(unittest.TestCase):
    def test_ids_text_and_sections(self):
        eps, sys, r = parse(DOCUMENT)
        self.assertEqual(eps.id, "LM-EPS-002")
        self.assertTrue(eps.text.startswith("The EPS shall light a light below:\n\n- 26.5 V"))
        self.assertEqual(eps.section, ("Power",))

    def test_options_are_links_and_attributes(self):
        _, sys, r = parse(DOCUMENT)
        self.assertEqual(sys.satisfies, ("TOP-1", "TOP-2"))
        self.assertEqual(sys.attributes, {"subsystem": "SYSTEM",
                                          "last-modified-by": "someone else"})
        self.assertEqual((r.satisfies, r.attributes), ((), {}))

    def test_sphinx_directives_and_roles_are_allowed(self):
        (r,) = parse("T\n=\n\n.. toctree::\n   :maxdepth: 2\n\n   power\n\n"
                     "See :doc:`power`.\n\n.. requirement:: A-1\n\n   x shall y\n")
        self.assertEqual(r.id, "A-1")

    def test_plain_text_ignores_markup_and_wrapping(self):
        self.assertEqual(plain_text("The *LGC*  shall\nshow:\n\n- one;\n- two."),
                         "The LGC shall show: one; two.")

    def test_repeated_ids_and_empty_text_are_errors(self):
        with self.assertRaises(RequirementsError):
            parse(".. requirement:: A-1\n\n   x\n\n.. requirement:: A-1\n\n   y\n")
        with self.assertRaises(RequirementsError):
            parse(".. requirement:: A-1\n")

    def test_parsing_does_not_pollute_global_docutils_directives(self):
        from docutils.parsers.rst import directives
        before = dict(directives._directives)
        parse(".. toctree::\n\n   power\n\n.. requirement:: A-1\n\n   x shall y\n")
        self.assertEqual(directives._directives, before)
        self.assertNotIn("toctree", directives._directives)
        self.assertNotIn("requirement", directives._directives)


class TestRendering(unittest.TestCase):
    def test_one_paragraph_renders_inline(self):
        html = requirement_html(Requirement("R-1", "The LGC shall run."))
        self.assertEqual(html, '<span class="ui-requirement">The LGC '
                               '<strong>shall [R-1]</strong> run.</span>')

    def test_lists_render_as_blocks(self):
        (eps, *_) = parse(DOCUMENT)
        html = requirement_html(Requirement(eps.id, eps.text))
        self.assertIn('<div class="ui-requirement ui-requirement--blocks">', html)
        self.assertIn("<li><p>26.5 V: the BATTERY caution;</p></li>", html)
        self.assertIn("<strong>shall [LM-EPS-002]</strong>", html)

    def test_text_is_escaped(self):
        html = requirement_html(Requirement("R", "Small (<3 degree) shall be"))
        self.assertIn("(&lt;3 degree)", html)


if __name__ == "__main__":
    unittest.main()
