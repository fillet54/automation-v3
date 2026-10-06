from automationv3.framework.block import BuildingBlock, BlockResult
from automationv3.framework import edn, html


class Wait(BuildingBlock):
    """Wait a number of seconds.

    .. note:: A stand-in for now: it passes straight away, without
       waiting.

    Example::

        (Wait 2)
    """

    def check_syntax(self, *args):
        return len(args) == 1

    def execute(self, seconds):
        return BlockResult(True)

    def as_html(self, seconds):
        return f"<span><strong>Wait</strong> {seconds} seconds</span>"


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
