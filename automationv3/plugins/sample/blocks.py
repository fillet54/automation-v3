"""Sample BuildingBlocks for the demo UUT"""

import json

from automationv3.framework import context, edn, markup
from automationv3.framework.block import BlockResult, BuildingBlock
from automationv3.framework.steps import attach

MODE = edn.Keyword("mode")
READINGS = edn.Keyword("readings")


class StartDemo(BuildingBlock):
    """Restart the demo UUT from a configuration map.

    ``:mode`` is required; ``:readings`` maps reading names to the values
    to set. Restarting clears earlier readings and faults. Values may use
    the script's definitions and variation symbols. In a rendered script
    the configuration reads as written, as a table.

    Example::

        (StartDemo {:mode :emergency
                    :readings {:brake-pressure 70}})
    """

    def usage(self):
        return "(StartDemo {:mode mode :readings {name value ...}})"

    def check_syntax(self, *args):
        return len(args) == 1 and isinstance(args[0], dict) and MODE in args[0]

    def execute(self, config):
        demo = context.lookup("demo")
        demo.start(config[MODE])
        readings = config.get(READINGS, {})
        for name, value in readings.items():
            demo.set(name, value)
        return BlockResult(
            True,
            stdout=f"started in {edn.writes(config[MODE])} "
                   f"with {len(readings)} reading(s)",
        )

    def as_rst(self, config):
        return markup.strong("Start the demo UUT") + "\n\n" + markup.mapping(
            config, caption="Configuration")


class SnapshotDemo(BuildingBlock):
    """Attach the demo UUT's state to the run as ``<label>.json``.

    The file holds the installed version, mode, readings and faults, and
    is listed with the step on the run page.

    Example::

        (SnapshotDemo "after-braking")
    """

    def check_syntax(self, *args):
        return len(args) == 1 and isinstance(args[0], str)

    def execute(self, label):
        demo = context.lookup("demo")
        name = f"{label}.json"
        attach(name, json.dumps(demo.uut.state(demo.env), indent=2, sort_keys=True))
        return BlockResult(True, stdout=f"attached {name}")

    def as_rst(self, label):
        return markup.line(markup.strong("Snapshot the demo UUT"), "as",
                           markup.code(f"{markup.written(label)}.json"))


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

    def check_syntax_forms(self, *args):
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

    def as_rst(self, *args):
        headers, rows = args
        return markup.table([str(h) for h in headers], rows)
