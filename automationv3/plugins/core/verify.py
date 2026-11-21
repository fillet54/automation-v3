"""Verify: check a value, with a predicate or by itself (see wait.py
for waiting on one)

A check is written ``actual predicate args...`` or ``value``. The
predicate is any function: it is called with the actual value, then the
args, and the check holds if it returns something truthy. The
comparisons (``= not= < <= > >=``) are predicates like any other.

The actual value and any arg may be a ref, read for the check (by the
Read that accepts it), or a group, checked member by member: every
member for Verify (VerifyAll), at least one for VerifyAny. A group with
single values or refs checks each member with them; groups together
pair members by position, and need as many.
"""

from dataclasses import dataclass, field

from automationv3.framework import context, edn, markup, refs
from automationv3.framework.block import ASSERTION, BlockResult, BuildingBlock
from automationv3.framework.refs import is_ref, members


@dataclass
class Check:
    """A check as written: `actual predicate args...`, or `actual` alone
    (predicate None), and its options (name -> form)"""

    actual: object
    predicate: object = None
    args: list = field(default_factory=list)
    options: dict = field(default_factory=dict)

    def written(self):
        """The check's own forms, without options"""
        return [self.actual] + ([self.predicate, *self.args]
                                if self.predicate is not None else [])

    def forms(self):
        """The forms the check evaluates"""
        return self.written() + list(self.options.values())


def names_predicate(form):
    """True if `form` can be a predicate as written: a name, or a call
    that gives one (e.g. (fn [v] ...)); not a number, string or keyword"""
    if isinstance(form, edn.Keyword):
        return False
    return isinstance(form, (edn.Symbol, edn.List))


def parse(forms, options=(), predicates=True):
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
    if predicates and len(forms) >= 2 and names_predicate(forms[1]):
        return Check(forms[0], forms[1], forms[2:], found)
    return None


def _side(value):
    """[(label or None, value)] for one value of a check: a ref's
    members, read, or a plain value"""
    if is_ref(value):
        return [(c.label, refs.read(c)) for _, c in members(value)]
    return [(None, value)]


def _shown(label, value):
    return f"{label} ({edn.writes(value)})" if label is not None else edn.writes(value)


def _paired(values):
    """Rows of the sides of `values` (the actual, then each arg), one
    per member: groups pair by position, single values repeat"""
    sizes = [len(members(v)) for v in values if is_ref(v) and len(members(v)) > 1]
    if len(set(sizes)) > 1:
        raise ValueError(f"can't pair a group of {sizes[0]} with a group of "
                         f"{next(n for n in sizes if n != sizes[0])}: "
                         "groups compared need as many members")
    sides = [_side(v) for v in values]
    rows = max(len(side) for side in sides)
    return list(zip(*[side * rows if len(side) == 1 else side for side in sides]))


def compare(actual, predicate=None, args=(), mode="all", written=None, name=None):
    """Whether a check holds, and what it checked, one line per member.
    `predicate` is called with the actual value, then `args`; None
    checks the value is truthy. `mode` is "all" or "any" (of a group's
    members), or "same" (they all read the same). `written` and `name`
    are the actual and the predicate as the script wrote them."""
    if mode == "same":
        if not is_ref(actual):
            raise TypeError(f"{edn.writes(written or actual)} isn't a group of refs")
        left = _side(actual)
        values = [value for _, value in left]
        passed = all(v == values[0] for v in values[1:])
        return passed, "\n".join(_shown(label, value) for label, value in left)
    if predicate is None:
        rows = _paired([actual])
        results = [bool(value) for ((_, value),) in rows]
    else:
        name = edn.writes(name) if name is not None else getattr(predicate, "__name__", "?")
        if not callable(predicate):
            raise TypeError(f"{name} isn't a predicate: it is {edn.writes(predicate)}, "
                            "not a function")
        rows = _paired([actual, *args])
        results = [bool(predicate(*[value for _, value in row])) for row in rows]
    lines = []
    for row, passed in zip(rows, results):
        (label, value), rest = row[0], row[1:]
        if predicate is None:
            line = _shown(label, value) if label is not None else \
                f"{edn.writes(written)} is {edn.writes(value)}"
        else:
            line = " ".join([_shown(label, value), name, *[_shown(*side) for side in rest]])
        if len(rows) > 1:
            line += "" if passed else "  <- no"
        lines.append(line)
    passed = any(results) if mode == "any" else all(results)
    return passed, "\n".join(lines)


def run_check(check, mode):
    """Evaluate a Check in the running script: (passed, what it checked)"""
    actual = context.evaluate(check.actual)
    if check.predicate is None:
        return compare(actual, mode=mode, written=check.actual)
    predicate = context.evaluate(check.predicate)
    args = [context.evaluate(arg) for arg in check.args]
    return compare(actual, predicate, args, mode, check.actual, check.predicate)


class Verify(BuildingBlock):
    """Check a value with a predicate, or that a value is truthy.

    An assertion: it fails the step when the check comes out false.
    ``predicate`` is any function, built in or the script's own: it is
    called with the actual value, then the args, if any, and the check
    holds if it returns something truthy. The comparisons
    ``= == != not= < <= > >=`` are predicates that take one arg.
    Everything is evaluated in the running script, so it can use
    definitions, variation symbols, UUT handles and refs. The step
    prints what it checked, with the values, e.g. ``60 <= 80``.

    A ref, as the actual value or an arg, is read, by whichever Read
    accepts it, so the predicate gets values. A group is checked member
    by member, and every member has to pass (Verify is VerifyAll); see
    VerifyAny. To check a group's members agree with each other, use
    ``same?``.

    Examples::

        (Verify (abs (Read touchdown.vz)) <= touchdown-vz-limit)
        (Verify (lm-ready? :standard :pdi))
        (Verify nav.mode = :run)
        (Verify nav.time > 10)
        (Verify nav.error some?)               ; a predicate without args
        (Verify nav.time within? 10 20)        ; the script's own:
                                               ; (defn within? [v lo hi] ...)
        (Verify cpu.nav.mode = :run)           ; cpu1's and cpu2's
        (Verify left.cmd = right.echo)
        (Verify (same? cpu.nav.solution))
    """

    kind = ASSERTION
    mode = "all"
    options = ()

    def usage(self):
        return f"({self.name()} actual predicate args...)\n({self.name()} value)"

    def check_syntax_forms(self, *forms):
        return parse(forms, self.options) is not None

    def evaluated_forms(self, *forms):
        return parse(forms, self.options).forms()

    def execute_forms(self, *forms):
        passed, compared = run_check(parse(forms, self.options), self.mode)
        return BlockResult(passed, stdout=compared)

    def as_rst(self, *forms):
        return markup.line(markup.strong(self.name()), markup.code(*forms))


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
