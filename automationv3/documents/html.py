"""Live HTML for documents: docutils' HTML, with a few classes given the
app's look

- a container classed ``collapsible`` becomes <details>, its first
  paragraph the <summary>; it starts open when something in it failed,
  errs, is running, or has an error diagnostic;
- a verdict (``:verdict:`fail```) becomes `hooks.verdict(state)`, the
  app's outcome badge, when given;
- `hooks.decorate(node)` may return HTML to add after an element (live
  controls: see web/documents.py).

Everything else is docutils' HTML5, styled by the app's stylesheet.
Exported sites and PDFs never go through this: they render the same
classes their own way.
"""

import functools
import re
from datetime import datetime, timezone
from html import escape

import docutils.core
from docutils import nodes
from docutils.writers.html5_polyglot import HTMLTranslator, Writer

from ..framework.rst import mark_shall
from . import core

ONE_PARAGRAPH = re.compile(r"\A\s*<p>(.*)</p>\s*\Z", re.DOTALL)


@functools.lru_cache(maxsize=1024)
def _render_requirement(req_id, text):
    """HTML for a requirement's text: inline if it is one paragraph,
    else blocks (lists, several paragraphs)"""
    try:
        tree = docutils.core.publish_doctree(
            text, settings_overrides={
                "report_level": 5, "halt_level": 5,
                "doctitle_xform": False, "file_insertion_enabled": False,
                "raw_enabled": False,  # text comes from imports: never raw HTML
            })
        mark_shall(tree, req_id, classes=())
        html = core.write(tree, "html5", {"initial_header_level": 4})["fragment"]
    except Exception:
        html = f"<p>{escape(text)}</p>"
    inline = ONE_PARAGRAPH.match(html)
    if inline and "<p>" not in inline.group(1):
        return f'<span class="ui-requirement">{inline.group(1)}</span>'
    return f'<div class="ui-requirement ui-requirement--blocks">{html}</div>'


def requirement_html(requirement):
    """HTML for a Requirement, with each 'shall' marked with its id"""
    if requirement.text:
        return _render_requirement(requirement.id, requirement.text)
    return f'<span class="ui-requirement"><strong>[{escape(requirement.id)}]</strong></span>'

OPEN = {"fail", "error", "running", "blocked"}


class Hooks:
    def verdict(self, state):
        return None

    def block_attributes(self, node):
        """Extra attributes for a live data block (see core.resolve)"""
        return ""

    def summary_icon(self):
        return ""

    def decorate(self, node):
        return None


def opens(node):
    """Whether a collapsible starts open"""
    for found in node.findall(nodes.Element):
        classes = set(found.get("classes", []))
        if found is not node and "collapsible" in classes:
            continue
        if ({"result", "table-row"} & classes and OPEN & classes) or \
                found.get("verdict") in OPEN or ({"diagnostic", "error"} <= classes):
            return True
    return bool(OPEN & set(node.get("classes", [])) and "table-row" in node["classes"])


class LiveTranslator(HTMLTranslator):
    hooks = Hooks()

    def visit_container(self, node):
        if "data-block" in node["classes"]:
            self.body.append(f'<div class="data-block" id="block-{node["serial"]}"'
                             f'{self.hooks.block_attributes(node)}>')
            return
        if "collapsible" in node["classes"]:
            classes = " ".join(node["classes"])
            self.body.append(f'<details class="{classes}"{" open" if opens(node) else ""}>')
            node["_summary"] = next((c for c in node.children
                                     if isinstance(c, nodes.paragraph)), None)
            return
        super().visit_container(node)

    def depart_container(self, node):
        if "data-block" in node["classes"]:
            self.body.append("</div>\n")
            return
        if "collapsible" in node["classes"]:
            self.body.append("</details>\n")
        else:
            super().depart_container(node)
        extra = self.hooks.decorate(node)
        if extra:
            self.body.append(extra)

    def visit_paragraph(self, node):
        parent = node.parent
        if isinstance(parent, nodes.container) and parent.get("_summary") is node:
            self.body.append(f"<summary>{self.hooks.summary_icon()}")
            return
        super().visit_paragraph(node)

    def depart_paragraph(self, node):
        parent = node.parent
        if isinstance(parent, nodes.container) and parent.get("_summary") is node:
            self.body.append("</summary>\n")
            return
        super().depart_paragraph(node)

    def visit_inline(self, node):
        if node.get("since"):  # :elapsed:, counted on by static/js/elapsed.js
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self.body.append(f'<span class="duration elapsed" data-since="{escape(node["since"])}" '
                             f'data-now="{now}">{escape(node.astext())}</span>')
            raise nodes.SkipNode
        if node.get("verdict"):
            badge = self.hooks.verdict(node["verdict"])
            if badge is not None:
                self.body.append(badge)
                raise nodes.SkipNode
        super().visit_inline(node)


class LiveWriter(Writer):
    def __init__(self, hooks=None):
        super().__init__()
        translator = type("Translator", (LiveTranslator,), {"hooks": hooks or Hooks()})
        self.translator_class = translator


def render(document, hooks=None):
    """The HTML of a resolved document's body"""
    return core.write(document, LiveWriter(hooks), {"initial_header_level": 3})["body"]
