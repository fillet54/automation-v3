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

from docutils import nodes
from docutils.writers.html5_polyglot import HTMLTranslator, Writer

from . import core

OPEN = {"fail", "error", "running", "blocked"}


class Hooks:
    def verdict(self, state):
        return None

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
        if ({"result", "table-row", "verdict"} & classes and OPEN & classes) or \
                ({"diagnostic", "error"} <= classes):
            return True
    return bool(OPEN & set(node.get("classes", [])) and "table-row" in node["classes"])


class LiveTranslator(HTMLTranslator):
    hooks = Hooks()

    def visit_container(self, node):
        if "collapsible" in node["classes"]:
            classes = " ".join(node["classes"])
            self.body.append(f'<details class="{classes}"{" open" if opens(node) else ""}>')
            node["_summary"] = next((c for c in node.children
                                     if isinstance(c, nodes.paragraph)), None)
            return
        super().visit_container(node)

    def depart_container(self, node):
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

    def visit_strong(self, node):
        if "verdict" in node["classes"]:
            badge = self.hooks.verdict(node.astext())
            if badge is not None:
                self.body.append(badge)
                raise nodes.SkipNode
        super().visit_strong(node)


class LiveWriter(Writer):
    def __init__(self, hooks=None):
        super().__init__()
        translator = type("Translator", (LiveTranslator,), {"hooks": hooks or Hooks()})
        self.translator_class = translator


def render(document, hooks=None):
    """The HTML of a resolved document's body"""
    return core.write(document, LiveWriter(hooks), {"initial_header_level": 3})["body"]
