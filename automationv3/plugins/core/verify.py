"""Verify: check a value, a comparison, or refs (see wait.py for
waiting on one)

A check is written ``actual op expected`` or ``value``. Either side may
be a ref, read for the check (by the Read that accepts it), or a group,
checked member by member: every member for Verify (VerifyAll), at
least one for VerifyAny. A group against a single value or ref
compares each member with it; a group against a group pairs members by position, and
both need as many.
"""

import operator
from dataclasses import dataclass, field

from automationv3.framework import context, edn, html, refs
from automationv3.framework.block import ASSERTION, BlockResult, BuildingBlock
from automationv3.framework.refs import is_ref, members

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


@dataclass
class Check:
    """A check as written: `actual op expected`, or `actual` alone (op and
    expected None), and its options (name -> form)"""

    actual: object
    op: object = None
    expected: object = None
    options: dict = field(default_factory=dict)

    def forms(self):
        """The forms the check evaluates"""
        found = [self.actual] + ([self.expected] if self.op is not None else [])
        return found + list(self.options.values())


def parse(forms, options=(), comparisons=True):
    """The Check `forms` write, or None. Trailing `:name value` pairs
    whose name is in `options` are options."""
    forms, found = list(forms), {}
    while (len(forms) >= 3 and isinstance(forms[-2], edn.Keyword)
           and str(forms[-2]).lstrip(":") in options):
        name = str(forms[-2]).lstrip(":")
        if name in found:
            return None
        found[name] = forms[-1]
        forms = forms[:-2]
    if len(forms) == 1:
        return Check(forms[0], options=found)
    if comparisons and len(forms) == 3 and str(forms[1]) in OPERATORS \
            and isinstance(forms[1], edn.Symbol):
        return Check(forms[0], forms[1], forms[2], found)
    return None


def _side(value):
    """[(label or None, value)] for one side of a check: a ref's
    members, read, or a plain value"""
    if is_ref(value):
        return [(c.label, refs.read(c)) for _, c in members(value)]
    return [(None, value)]


def _shown(label, value):
    return f"{label} ({show(value)})" if label is not None else show(value)


def compare(actual, op=None, expected=None, mode="all", written=None):
    """Whether a check holds, and what it compared, one line per pair.
    `mode` is "all" or "any" (of a group's members), or "same" (they all
    read the same)."""
    if op is not None and is_ref(actual) and is_ref(expected):
        sizes = len(members(actual)), len(members(expected))
        if min(sizes) > 1 and sizes[0] != sizes[1]:
            raise ValueError(f"can't pair a group of {sizes[0]} with a group of "
                             f"{sizes[1]}: groups compared need as many members")
    left = _side(actual)
    if mode == "same":
        if not is_ref(actual):
            raise TypeError(f"{show(written or actual)} isn't a group of refs")
        values = [value for _, value in left]
        passed = all(v == values[0] for v in values[1:])
        return passed, "\n".join(_shown(label, value) for label, value in left)
    if op is None:
        pairs = [(item, None) for item in left]
        results = [bool(value) for _, value in left]
    else:
        right = _side(expected)
        if len(right) == 1:
            right = right * len(left)
        elif len(left) == 1:
            left = left * len(right)
        pairs = list(zip(left, right))
        check = OPERATORS[str(op)]
        results = [bool(check(lv, rv)) for (_, lv), (_, rv) in pairs]
    lines = []
    for ((llabel, lvalue), right), passed in zip(pairs, results):
        if right is None:
            line = _shown(llabel, lvalue) if llabel is not None else \
                f"{show(written)} is {show(lvalue)}"
        else:
            line = f"{_shown(llabel, lvalue)} {op} {_shown(*right)}"
        if len(pairs) > 1:
            line += "" if passed else "  <- no"
        lines.append(line)
    passed = any(results) if mode == "any" else all(results)
    return passed, "\n".join(lines)


def run_check(check, mode):
    """Evaluate a Check in the running script: (passed, what it compared)"""
    actual = context.evaluate(check.actual)
    expected = context.evaluate(check.expected) if check.op is not None else None
    return compare(actual, check.op, expected, mode, written=check.actual)


class Verify(BuildingBlock):
    """Check a value against an expected one, or that a value is truthy.

    An assertion: it fails the step when the check comes out false.
    Both sides are evaluated in the running script, so they can use
    definitions, variation symbols, UUT handles and refs. ``op``
    is one of ``= == != not= < <= > >=``, written as is. The step
    prints what it compared, with the values, e.g. ``60 <= 80``.

    A ref on either side is read, by whichever Read accepts it. A
    group is checked member by member, and every member has to pass
    (Verify is VerifyAll); see VerifyAny. To check a group's members agree with each other, use
    ``same?``.

    Examples::

        (Verify (reading :brake-pressure) <= max-pressure)
        (Verify (demo-in-mode? :normal))
        (Verify nav.mode = :run)
        (Verify cpu.nav.mode = :run)           ; cpu1's and cpu2's
        (Verify left.cmd = right.echo)
        (Verify (same? cpu.nav.solution))
    """

    kind = ASSERTION
    mode = "all"
    options = ()

    def usage(self):
        return f"({self.name()} actual op expected)\n({self.name()} value)"

    def check_syntax_forms(self, *forms):
        return parse(forms, self.options) is not None

    def evaluated_forms(self, *forms):
        return parse(forms, self.options).forms()

    def execute_forms(self, *forms):
        passed, compared = run_check(parse(forms, self.options), self.mode)
        return BlockResult(passed, stdout=compared)

    def as_html(self, *forms):
        return (
            f"<span><strong>{self.name()}</strong> "
            f'<span class="ui-mono">{" ".join(html.text(f) for f in forms)}</span>'
            "</span>"
        )


class VerifyAll(Verify):
    """Verify, by its other name: a group passes only if every member
    does.

    Example::

        (VerifyAll cpu.nav.mode = :run)
    """


class VerifyAny(Verify):
    """Check a group (or a single ref, or a value) like Verify, but
    pass if any one member passes.

    Example::

        (VerifyAny transponders.on)
        (VerifyAny cpu.role = :primary)
    """

    mode = "any"
