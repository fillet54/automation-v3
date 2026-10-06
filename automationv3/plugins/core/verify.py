import operator

from automationv3.framework import context, edn, html
from automationv3.framework.block import BlockResult, BuildingBlock

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
    """Check a value::

        (Verify (reading :brake-pressure) <= max-pressure)
        (Verify (demo-in-mode? :normal))

    Both sides are evaluated in the running script. The operator is one
    of = == != not= < <= > >=; with a single form, it must be truthy.
    """

    def check_syntax(self, *forms):
        if len(forms) == 1:
            return True
        return len(forms) == 3 and str(forms[1]) in OPERATORS

    # The operator is syntax, so the block takes its forms as written
    def execute_forms(self, *forms):
        if len(forms) == 1:
            value = context.evaluate(forms[0])
            return BlockResult(bool(value), stdout=f"{show(forms[0])} is {show(value)}")

        actual, op, expected = forms
        actual_value = context.evaluate(actual)
        expected_value = context.evaluate(expected)
        passed = OPERATORS[str(op)](actual_value, expected_value)
        return BlockResult(
            bool(passed),
            stdout=f"{show(actual_value)} {op} {show(expected_value)}",
        )

    def as_html(self, *forms):
        return (
            "<span><strong>Verify</strong> "
            f'<span class="ui-mono">{" ".join(html.text(f) for f in forms)}</span>'
            "</span>"
        )
