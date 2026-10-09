"""Wait: until a check holds (see verify.py for checks), or for a time"""

from automationv3.framework import connectors, context, edn, html
from automationv3.framework.block import ASSERTION, BlockResult, BuildingBlock
from automationv3.framework.steps import current_runtime

from .verify import parse, run_check, show


class Wait(BuildingBlock):
    """Wait until a check holds, or for a time.

    The check is written as for Verify, and checked over and over (every
    100 ms, or ``:every``) until it holds or the time ``:within`` runs
    out, which fails the step. Without ``:within``, the time is
    ``wait-timeout`` if the script defines it, otherwise 10 s. On a
    group, every member has to hold at once (Wait is WaitAll); see
    WaitAny and WaitSame.

    With only a time, it waits that long: ``(Wait 2s)``.

    Times are in seconds, or time literals: ``500ms``, ``5s``,
    ``2min``, ``1h``. A UUT with a clock of its own (a simulation) keeps
    the time; otherwise it is the wall clock's.

    Examples::

        (Wait nav.mode = :run :within 5s)
        (Wait cpu.nav.mode = :run :within 10s :every 500ms)
        (Wait (Telemetry :mode) = :safe :within 2min)
        (Wait 2s)
    """

    kind = ASSERTION
    mode = "all"
    options = ("within", "every")

    def usage(self):
        return (f"({self.name()} actual op expected :within time? :every time?)\n"
                f"({self.name()} value :within time? :every time?)\n"
                f"({self.name()} time)")

    def check_syntax(self, *forms):
        return parse(forms, self.options) is not None

    def evaluated_forms(self, *forms):
        return parse(forms, self.options).forms()

    def execute_forms(self, *forms):
        check = parse(forms, self.options)
        options = {name: seconds(context.evaluate(form), name)
                   for name, form in check.options.items()}
        if check.op is None and not options and self.mode == "all":
            value = context.evaluate(check.actual)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                connectors.sleep(value)
                return BlockResult(True, stdout=f"waited {show(value)} s"
                                   if not isinstance(value, edn.Duration)
                                   else f"waited {show(value)}")
        within = options.get("within", default("wait-timeout", DEFAULT_TIMEOUT))
        every = options.get("every", default("wait-every", DEFAULT_EVERY))
        return poll(lambda: run_check(check, self.mode), within, every)

    def as_html(self, *forms):
        return wait_html(self, forms)


class WaitAll(Wait):
    """Wait, by its other name: on a group, every member has to hold at
    once.

    Example::

        (WaitAll cpu.nav.mode = :run :within 10s)
    """


class WaitAny(Wait):
    """Wait until the check holds for any one member of a group.

    Example::

        (WaitAny cpu.role = :primary :within 30s)
    """

    mode = "any"


class WaitSame(Wait):
    """Wait until every member of a group reads the same.

    Example::

        (WaitSame cpu.nav.solution :within 5s)
    """

    mode = "same"

    def usage(self):
        return "(WaitSame group :within time? :every time?)"

    def check_syntax(self, *forms):
        check = parse(forms, self.options, comparisons=False)
        return check is not None

    def evaluated_forms(self, *forms):
        return parse(forms, self.options, comparisons=False).forms()

    def execute_forms(self, *forms):
        check = parse(forms, self.options, comparisons=False)
        options = {name: seconds(context.evaluate(form), name)
                   for name, form in check.options.items()}
        within = options.get("within", default("wait-timeout", DEFAULT_TIMEOUT))
        every = options.get("every", default("wait-every", DEFAULT_EVERY))
        return poll(lambda: run_check(check, self.mode), within, every)


def wait_html(block, forms):
    """Wait 2 seconds, or Wait until <check> within 5s every 1s"""
    name = f"<strong>{block.name()}</strong>"
    check = parse(forms, block.options, comparisons=block.mode != "same")
    if check is None:
        return f"<span>{name} {' '.join(html.text(f) for f in forms)}</span>"
    if (not check.options and block.mode == "all" and check.op is None
            and isinstance(check.actual, (int, float))
            and not isinstance(check.actual, bool)):
        unit = "" if isinstance(check.actual, edn.Duration) else " seconds"
        return f"<span>{name} {html.text(check.actual)}{unit}</span>"
    written = [check.actual] + ([check.op, check.expected] if check.op is not None else [])
    until = " ".join(html.text(f) for f in written)
    text = f'<span>{name} until <span class="ui-mono">{until}</span>'
    for option in ("within", "every"):
        if option in check.options:
            text += f' {option} <span class="ui-mono">{html.text(check.options[option])}</span>'
    return text + "</span>"


DEFAULT_TIMEOUT = edn.Duration(10.0, "10s")
DEFAULT_EVERY = edn.Duration(0.1, "100ms")


def seconds(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise TypeError(f":{name} takes a time, e.g. 5s or 500ms, not {show(value)}")
    return value


def default(name, fallback):
    """A script's own default (e.g. (def wait-timeout 30s)), or `fallback`"""
    try:
        return seconds(context.lookup(name), name)
    except KeyError:
        return fallback


def shown_time(value):
    return show(value) if isinstance(value, edn.Duration) else f"{value:g}s"


def poll(check, within, every):
    """Run `check` until it passes or `within` seconds pass; its block
    calls run silently, so polling doesn't flood the report"""
    runtime = current_runtime()
    started = connectors.clock()
    while True:
        with runtime.within(silent=True):
            passed, compared = check()
        waited = connectors.clock() - started
        if passed:
            return BlockResult(True, stdout=f"after {waited:g}s: {compared}")
        if waited >= within:
            return BlockResult(False, stdout=f"not within {shown_time(within)}: "
                                             f"{compared}")
        connectors.sleep(min(every, within - waited) if every > 0 else within - waited)


class SetupSimulation(BuildingBlock):
    """Configure the simulation from pairs of names and values.

    Names and values are taken as written, not evaluated, and rendered as
    a code block.

    .. note:: A sample: it passes without configuring anything.

    Example::

        (SetupSimulation
          :speed 50
          :road "wet")
    """

    def usage(self):
        return "(SetupSimulation name value ...)"

    def check_syntax(self, *args):
        return (len(args) % 2) == 0

    # Keys and values are names as written, e.g. [xyz]
    def execute_forms(self, *arg):
        return BlockResult(True)

    def as_rst(self, *args):
        lines = [".. code-block:: clojure", "", "   (SetupSimulation"]
        # TODO: Clean this up
        for arg1, arg2 in zip(args[::2], args[1::2]):
            if isinstance(arg1, str) and not isinstance(
                arg1, (edn.Symbol, edn.Keyword)
            ):
                arg1 = f'"{arg1}"'
            if isinstance(arg2, str) and not isinstance(
                arg2, (edn.Symbol, edn.Keyword)
            ):
                arg2 = f'"{arg2}"'
            lines.append(f"      {arg1} {arg2}")
        lines[-1] += ")\n\n"

        return "\n".join(lines)


class TableDriven(BuildingBlock):
    """A table of cases: named columns, one row per case.

    ``headers`` is a vector of bare symbols naming the columns; ``rows`` is
    a vector of rows, each a vector of values in column order. The step
    renders as the table.

    .. note:: A sample of a block that renders itself: it passes without
       running the cases.

    Example::

        (Table-Driven [mode pressure]
                      [[:normal 60]
                       [:limp-home 75]])
    """

    def usage(self):
        return "(Table-Driven [header ...] [[value ...] ...])"

    def name(self):
        return "Table-Driven"

    # Headers are bare symbols naming columns, not values to evaluate
    def execute_forms(self, *args):
        return BlockResult(True)

    def as_html(self, *args):
        headers, rows = args
        return html.table([str(h) for h in headers], rows)
