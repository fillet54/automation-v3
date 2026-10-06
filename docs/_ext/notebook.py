"""Small additions for these docs

- Pages depend on the stylesheet, so editing _static/css/notebook.css
  rebuilds them (and copies it) rather than being skipped as up to date.
- :status:`passed` shows a run outcome the way the web UI badges it.
- ``.. building-blocks::`` documents every BuildingBlock the plugins
  define, from the blocks themselves: each block's `usage()` and its
  docstring (reStructuredText), grouped by plugin. Give a plugin package
  as the argument to document only its blocks.
"""

import importlib
import inspect
from pathlib import Path

from docutils import nodes
from docutils.statemachine import StringList
from sphinx.util.docutils import SphinxDirective
from sphinx.util.nodes import nested_parse_with_titles

STATUSES = {"passed", "failed", "error", "partial", "blocked", "running", "queued",
            "skipped", "not identical"}

PLUGINS = "automationv3.plugins"

STYLESHEET = Path(__file__).resolve().parent.parent / "_static" / "css" / "notebook.css"


def status_role(name, rawtext, text, lineno, inliner, options=None, content=()):
    word = text.strip().lower()
    if word not in STATUSES:
        message = inliner.reporter.error(f"unknown status {text!r}", line=lineno)
        return [inliner.problematic(rawtext, rawtext, message)], [message]
    css = "ui-status-word ui-status-word--" + word.replace(" ", "-")
    return [nodes.inline(rawtext, word, classes=css.split())], []


def plugin_of(block):
    """The plugin package a block is defined in, e.g. automationv3.plugins.core"""
    module = type(block).__module__
    if not module.startswith(PLUGINS + "."):
        return None
    return ".".join(module.split(".")[:3])


def blocks_by_plugin():
    """plugin package -> its blocks, sorted by name"""
    from automationv3.framework.block import all_blocks

    found = {}
    for block in all_blocks():
        plugin = plugin_of(block)
        if plugin is not None:
            found.setdefault(plugin, []).append(block)
    return {plugin: sorted(blocks, key=lambda b: b.name())
            for plugin, blocks in sorted(found.items())}


def indent(text, prefix="   "):
    return [prefix + line if line else "" for line in text.splitlines()]


def heading(title, underline):
    return [title, underline * len(title), ""]


def block_rst(block):
    cls = type(block)
    lines = [f".. _block-{block.name()}:", "", *heading(block.name(), "~")]
    lines += [".. code-block:: clojure", "   :class: block-usage", "",
              *indent(block.usage()), ""]
    doc = block.doc()
    lines += doc.splitlines() if doc else ["*Not documented yet.*"]
    lines += ["", ".. rst-class:: block-source", "",
              f"``{cls.__module__}.{cls.__qualname__}``", ""]
    return lines


def plugin_rst(plugin, blocks, with_heading):
    lines = []
    if with_heading:
        lines += heading(f"The {plugin.rsplit('.', 1)[-1]} plugin", "-")
        summary = inspect.getdoc(importlib.import_module(plugin))
        if summary:
            lines += [*summary.splitlines(), ""]
    for block in blocks:
        lines += block_rst(block)
    return lines


class BuildingBlocks(SphinxDirective):
    optional_arguments = 1

    def run(self):
        by_plugin = blocks_by_plugin()
        if self.arguments:
            by_plugin = {p: b for p, b in by_plugin.items() if p == self.arguments[0]}
        lines = []
        for plugin, blocks in by_plugin.items():
            lines += plugin_rst(plugin, blocks, with_heading=not self.arguments)
        for plugin in by_plugin:
            for block in by_plugin[plugin]:
                self.env.note_dependency(inspect.getfile(type(block)))
        node = nodes.section()
        node.document = self.state.document
        content = StringList(lines, "<building-blocks>")
        nested_parse_with_titles(self.state, content, node)
        return node.children


def depend_on_stylesheet(app, docname, source):
    app.env.note_dependency(str(STYLESHEET))


def setup(app):
    app.connect("source-read", depend_on_stylesheet)
    app.add_role("status", status_role)
    app.add_directive("building-blocks", BuildingBlocks)
    return {"parallel_read_safe": True, "parallel_write_safe": True}
