"""What docutils does that plans/source-tree.md relies on

The one-parse design reads positions and structure from docutils. Some
of what it reads is undocumented (title lines, positions inside a
nested parse), so each fact is pinned here: a docutils upgrade that
changes one fails here first, not somewhere in cards or spans.

The directives and the role registered here have names of their own
(`fact-*`), so they don't touch the rvt ones.
"""

import io
import unittest
from pathlib import Path

from docutils import nodes
from docutils.core import publish_doctree
from docutils.parsers.rst import Directive, directives, roles

from automationv3.framework import rst, source  # noqa: F401  (registers rvt, rvt-variant, :req:)

ROOT = Path(__file__).resolve().parent.parent


class fact(nodes.Element):
    """What a fact directive saw"""


class FactDirective(Directive):
    has_content = True
    optional_arguments = 1
    final_argument_whitespace = True
    option_spec = {"text": directives.unchanged, "flag": directives.flag}

    def run(self):
        node = fact()
        node["lineno"] = self.lineno
        node["block_text"] = self.block_text
        node["content_offset"] = self.content_offset
        node["items"] = [offset for _, offset in self.content.items]
        node["options"] = dict(self.options)
        node["arguments"] = list(self.arguments)
        return [node]


class AnyOption(dict):
    """An option spec that takes any name, each as plain text"""

    def __bool__(self):  # docutils skips option parsing for an empty spec
        return True

    def __getitem__(self, name):
        return directives.unchanged

    def __contains__(self, name):
        return True

    def get(self, name, default=None):
        return directives.unchanged


class FactAnyDirective(FactDirective):
    option_spec = AnyOption()


class FactNestDirective(Directive):
    has_content = True

    def run(self):
        node = fact()
        node["lineno"] = self.lineno
        self.state.nested_parse(self.content, self.content_offset, node, match_titles=True)
        return [node]


class FactPlainNestDirective(FactNestDirective):
    """Nested parse without match_titles, as most directives do it"""

    def run(self):
        node = fact()
        self.state.nested_parse(self.content, self.content_offset, node)
        return [node]


def fact_role(name, rawtext, text, lineno, inliner, options=None, content=None):
    node = nodes.inline(rawtext, text)
    node["lineno"] = lineno
    return [node], []


directives.register_directive("fact", FactDirective)
directives.register_directive("fact-any", FactAnyDirective)
directives.register_directive("fact-nest", FactNestDirective)
directives.register_directive("fact-nest-plain", FactPlainNestDirective)
roles.register_canonical_role("fact-role", fact_role)


def parse(text, **settings):
    """The doctree of `text`, and what docutils wrote at warning level or
    above"""
    stream = io.StringIO()
    tree = publish_doctree(text, settings_overrides={
        "warning_stream": stream, "report_level": 2, "halt_level": 5, **settings})
    return tree, stream.getvalue()


def messages(tree):
    return [(m["level"], m.astext()) for m in tree.findall(nodes.system_message)]


def titles(tree):
    return [(t.astext(), t.line) for t in tree.findall(nodes.title)]


SCRIPT = """\
Title
=====

A paragraph whose second line has
a :fact-role:`ROLE-1` in it.

.. fact:: An argument
   :text: one

   first
     second

Section
-------

.. fact-nest::

   Inner
   ~~~~~

   :fact-role:`ROLE-2`

   .. fact::

      nested

      .. fact::

         deeper
"""


class DirectivePositions(unittest.TestCase):
    """A directive knows its own lines exactly, nested or not"""

    def setUp(self):
        self.tree, self.warnings = parse(SCRIPT)
        self.found = [n for n in self.tree.findall(fact) if "items" in n]

    def test_no_messages(self):
        self.assertEqual(self.warnings, "")

    def test_lineno_is_the_first_line(self):
        self.assertEqual([n["lineno"] for n in self.found], [7, 23])

    def test_block_text_is_its_lines(self):
        self.assertEqual(self.found[0]["block_text"],
                         ".. fact:: An argument\n   :text: one\n\n   first\n     second\n")

    def test_content_offset_is_the_line_before_the_content(self):
        # 0-based index of the content's first line = its 1-based line - 1
        self.assertEqual(self.found[0]["content_offset"], 9)
        self.assertEqual(self.found[1]["content_offset"], 24)

    def test_each_content_line_knows_its_file_line(self):
        # 0-based
        self.assertEqual(self.found[0]["items"], [9, 10])
        self.assertEqual(self.found[1]["items"], [24, 25, 26, 27, 28])

    def test_inside_a_nested_parse(self):
        # The inner fact (line 23) is inside fact-nest's content; its
        # content holds a third directive as text, not parsed
        nest = next(n for n in self.tree.findall(fact) if "items" not in n)
        self.assertEqual(nest["lineno"], 16)
        # under the nested "Inner" section, itself a child of fact-nest
        self.assertEqual(self.found[1].parent.tagname, "section")
        self.assertIs(self.found[1].parent.parent, nest)

    def test_three_levels(self):
        text = """\
.. fact-nest::

   .. fact-nest::

      .. fact-nest::

         .. fact::

            x
"""
        tree, warnings = parse(text)
        self.assertEqual(warnings, "")
        node = next(n for n in tree.findall(fact) if "items" in n)
        self.assertEqual((node["lineno"], node["items"]), (7, [8]))


class TitlePositions(unittest.TestCase):
    """A title's line is not its own: docutils gives the underline's at
    the top level and nothing inside a nested parse"""

    def test_top_level_title_line_is_the_underline(self):
        tree, _ = parse(SCRIPT, doctitle_xform=False)
        self.assertEqual(titles(tree), [("Title", 2), ("Section", 14), ("Inner", None)])

    def test_overlined_title_line_is_the_underline(self):
        tree, _ = parse("=====\nTitle\n=====\n\nText.\n", doctitle_xform=False)
        self.assertEqual(titles(tree), [("Title", 3)])

    def test_doctitle_transform_lifts_the_first_title(self):
        # By default a lone top section becomes the document's title, so
        # the tree no longer mirrors the file: the one parse turns it off
        tree, _ = parse(SCRIPT)
        self.assertEqual(tree.children[0].tagname, "title")
        tree, _ = parse(SCRIPT, doctitle_xform=False)
        self.assertEqual(tree.children[0].tagname, "section")

    def test_nested_title_needs_a_deeper_style(self):
        # Inside a nested parse only a style deeper than the enclosing
        # section's makes a title; one at its level or above is an error
        for style, level in (("-", 2), ("=", 1)):
            text = SCRIPT.replace("Inner\n   ~~~~~", f"Inner\n   {style * 5}")
            tree, _ = parse(text, doctitle_xform=False)
            self.assertNotIn("Inner", [t for t, _ in titles(tree)])
            self.assertIn(f"A level {level} section cannot be used here",
                          " ".join(m for _, m in messages(tree)))

    def test_nested_title_needs_match_titles(self):
        tree, _ = parse(SCRIPT.replace(".. fact-nest::", ".. fact-nest-plain::"))
        self.assertIn("Unexpected section title", " ".join(m for _, m in messages(tree)))


class SectionsNest(unittest.TestCase):

    def test_a_directive_under_a_heading_is_inside_its_section(self):
        tree, _ = parse(SCRIPT, doctitle_xform=False)
        top, inner = list(tree.findall(nodes.section))[:2]
        self.assertIs(top.parent, tree)
        self.assertIs(inner.parent, top)  # "Section" is under "Title"
        node = next(tree.findall(fact))
        self.assertIs(node.parent, top)


class RolePositions(unittest.TestCase):
    """An inline role knows only its paragraph's first line, no column"""

    def test_role_line_is_the_paragraphs(self):
        tree, _ = parse(SCRIPT)
        found = {n.astext(): n for n in tree.findall(nodes.inline)}
        self.assertEqual(found["ROLE-1"]["lineno"], 4)  # written on line 5
        self.assertEqual(found["ROLE-2"]["lineno"], 21)
        self.assertIsNone(found["ROLE-1"].line)


class RejectedDirectives(unittest.TestCase):
    """A directive docutils rejects leaves only a system_message"""

    def test_unknown_option(self):
        tree, _ = parse("Text.\n\n.. fact::\n   :bogus: 1\n\n   x\n")
        self.assertEqual(list(tree.findall(fact)), [])
        [message] = tree.findall(nodes.system_message)
        self.assertEqual(message["level"], 3)
        self.assertIn('unknown option: "bogus"', message.astext())
        self.assertIsNone(message.line)  # the node's own position is unset,
        self.assertEqual(message["line"], 3)  # only the attribute has it

    def test_any_option_spec_takes_any_name(self):
        tree, warnings = parse("Text.\n\n.. fact-any:: t\n   :bogus: 1\n   :flag:\n\n   x\n")
        self.assertEqual(warnings, "")
        [node] = tree.findall(fact)
        self.assertEqual(node["options"], {"bogus": "1", "flag": ""})
        self.assertEqual(node["items"], [6])

    def test_an_empty_option_spec_takes_no_options(self):
        # Why AnyOption is truthy: an empty spec reads as "no options"
        class Empty(AnyOption):
            def __bool__(self):
                return False

        class Directive_(FactDirective):
            option_spec = Empty()

        directives.register_directive("fact-empty", Directive_)
        tree, _ = parse(".. fact-empty::\n   :bogus: 1\n\n   x\n")
        [node] = tree.findall(fact)
        self.assertEqual(node["options"], {})

    def test_a_typed_converter_still_rejects(self):
        tree, _ = parse(".. fact::\n   :flag: yes\n\n   x\n")
        self.assertEqual(list(tree.findall(fact)), [])
        self.assertIn("invalid option value", " ".join(m for _, m in messages(tree)))


class Headings(unittest.TestCase):

    def test_level_skip_is_an_error(self):
        text = "A\n===\n\nB\n---\n\nC\n~~~\n\nD\n===\n\nE\n~~~\n"
        tree, _ = parse(text)
        [(level, message)] = messages(tree)
        self.assertEqual(level, 3)
        self.assertIn("Inconsistent title style: skip from level 1 to 3", message)

    def test_underline_under_four_characters_is_text(self):
        tree, warnings = parse("Para.\n\nHello there\n---\n")
        self.assertEqual(titles(tree), [])
        self.assertEqual(warnings, "")  # only an INFO message

    def test_underline_of_four_or_more_short_of_its_title_is_a_heading(self):
        tree, warnings = parse("Para.\n\nHello there\n----\n")
        self.assertEqual([t for t, _ in titles(tree)], ["Hello there"])
        self.assertIn("Title underline too short", warnings)


def scripts():
    """Every script and core.rst under test/data and demo"""
    return [path for top in ("test/data", "demo") for path in sorted((ROOT / top).rglob("*.rst"))
            if source.has_rvt(path.read_text())]


class WholeFiles(unittest.TestCase):

    def test_every_script_parses_without_messages(self):
        found = scripts()
        self.assertGreater(len(found), 80)
        for path in found:
            with self.subTest(path=str(path.relative_to(ROOT))):
                _, warnings = parse(path.read_text(), doctitle_xform=False)
                self.assertEqual(warnings, "")


if __name__ == "__main__":
    unittest.main()
