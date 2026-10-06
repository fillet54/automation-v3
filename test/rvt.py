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
