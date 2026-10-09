import operator

from automationv3.framework import context, edn, html
from automationv3.framework.block import ASSERTION, BlockResult, BuildingBlock

OPERATORS = {
    "=": operator.eq,
    "==": operator.eq,
    "!=": operator.ne,
    "not=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}


def show(value):
    return edn.writes(value)


class Verify(BuildingBlock):
    """Check a value against an expected one, or that a value is truthy.

    An assertion: it fails the step when the check comes out false.
    Both sides are evaluated in the running script, so they can use
    definitions, variation symbols and UUT handles. ``op`` is one of
    ``= == != not= < <= > >=``, written as is. The step prints what it
    compared, with the values, e.g. ``60 <= 80``.

    Examples::

        (Verify (reading :brake-pressure) <= max-pressure)
        (Verify (demo-in-mode? :normal))
    """

    def usage(self):
        return "(Verify actual op expected)\n(Verify value)"

    kind = ASSERTION
    quoted = {"op"}  # the operator is syntax: taken as written

    def check_syntax(self, *forms):
        if len(forms) == 1:
            return True
        return len(forms) == 3 and str(forms[1]) in OPERATORS

    def execute(self, actual, op=None, expected=None):
        if op is None:
            (written,) = context.written_args()
            return BlockResult(bool(actual), stdout=f"{show(written)} is {show(actual)}")
        passed = OPERATORS[str(op)](actual, expected)
        return BlockResult(bool(passed), stdout=f"{show(actual)} {op} {show(expected)}")

    def as_html(self, *forms):
        return (
            "<span><strong>Verify</strong> "
            f'<span class="ui-mono">{" ".join(html.text(f) for f in forms)}</span>'
            "</span>"
        )
