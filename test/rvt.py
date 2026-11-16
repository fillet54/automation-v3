"""Helpers for writing script fixtures: rst documents with rvt blocks"""

import textwrap


def rvt(code, *options, title=None, **values):
    """An rvt block holding `code`, e.g. rvt("(Wait 1)", "definitions"),
    rvt("(Wait 1)", variations="low, high") or rvt("(Wait 1)", title="Pause")"""
    head = f".. rvt::{' ' + title if title else ''}\n"
    head += "".join(f"   :{option}:\n" for option in options)
    head += "".join(f"   :{name}: {value}\n" for name, value in values.items())
    return head + "\n" + textwrap.indent(textwrap.dedent(code).strip(), "   ") + "\n"


def doc(*chunks):
    """A document from prose chunks and rvt blocks, separated by blank lines"""
    return "\n\n".join(textwrap.dedent(chunk).strip("\n") for chunk in chunks) + "\n"


def views(text):
    """A script's forms as pages show them (documents/script.view)"""
    from automationv3.documents import script
    from automationv3.framework import source
    return [script.view(s) for s in source.statements(source.parse(text))]


def page_entries(text, **options):
    """A script page's outer containers (documents/script.py), in order,
    as (classes, summary): a container's classes, and the text of its
    first paragraph if it is collapsible or scoped (else ""); each with
    the entries inside it as a third item"""
    from docutils import nodes

    from automationv3.documents import core, script

    def entries(node):
        found = []
        for child in node.children:
            if isinstance(child, nodes.container):
                classes = " ".join(child["classes"])
                first = child.children[0] if child.children else None
                summary = (first.astext() if isinstance(first, nodes.paragraph)
                           and ("collapsible" in classes or "scoped" in classes) else "")
                found.append((classes, summary, entries(child)))
            elif isinstance(child, nodes.section):
                found += entries(child)
        return found

    return entries(core.parse(script.render(text, **options)))
