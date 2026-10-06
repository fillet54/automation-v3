"""Helpers for writing script fixtures: rst documents with rvt blocks"""

import textwrap


def rvt(code, *options):
    """An rvt block holding `code`, e.g. rvt("(Wait 1)", "definitions")"""
    head = ".. rvt::\n" + "".join(f"   :{option}:\n" for option in options)
    return head + "\n" + textwrap.indent(textwrap.dedent(code).strip(), "   ") + "\n"


def doc(*chunks):
    """A document from prose chunks and rvt blocks, separated by blank lines"""
    return "\n\n".join(textwrap.dedent(chunk).strip("\n") for chunk in chunks) + "\n"
