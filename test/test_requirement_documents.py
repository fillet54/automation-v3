"""Requirements written in reStructuredText"""

import unittest

from automationv3.framework.requirement import Requirement
from automationv3.services.requirements.rst_source import RequirementsError, parse

DOCUMENT = """
Power
=====

Prose is ignored.

.. requirement:: VM-EPS-002

   The VM shall shed loads below:

   - 60%: the payload;
   - 40%: everything else.

.. requirement:: SYS-1
   :subsystem: SYSTEM

   The platform shall *survive*.

.. requirement:: R-1

   Plain shall be.
"""


class TestParsing(unittest.TestCase):
    def test_ids_text_and_subsystems(self):
        eps, sys, r = parse(DOCUMENT)
        self.assertEqual((eps.id, eps.subsystem), ("VM-EPS-002", "EPS"))
        self.assertTrue(eps.text.startswith("The VM shall shed loads below:\n\n- 60%"))
        self.assertEqual(sys.subsystem, "SYSTEM")
        self.assertEqual(r.subsystem, "R")

    def test_repeated_ids_and_empty_text_are_errors(self):
        with self.assertRaises(RequirementsError):
            parse(".. requirement:: A-1\n\n   x\n\n.. requirement:: A-1\n\n   y\n")
        with self.assertRaises(RequirementsError):
            parse(".. requirement:: A-1\n")


class TestRendering(unittest.TestCase):
    def test_one_paragraph_renders_inline(self):
        html = Requirement("R-1", "The VM shall run.").__repr_html__()
        self.assertEqual(html, '<span class="ui-requirement">The VM '
                               '<strong>shall [R-1]</strong> run.</span>')

    def test_lists_render_as_blocks(self):
        (eps, *_) = parse(DOCUMENT)
        html = eps.__repr_html__()
        self.assertIn('<div class="ui-requirement ui-requirement--blocks">', html)
        self.assertIn("<li>60%: the payload;</li>", html)
        self.assertIn("<strong>shall [VM-EPS-002]</strong>", html)

    def test_text_is_escaped(self):
        html = Requirement("R", "Small (<3 degree) shall be").__repr_html__()
        self.assertIn("(&lt;3 degree)", html)


if __name__ == "__main__":
    unittest.main()
