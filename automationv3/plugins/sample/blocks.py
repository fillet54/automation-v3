"""Sample BuildingBlocks for the demo UUT"""

import json

from automationv3.framework import context, edn, html
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

    def as_html(self, config):
        return (
            "<div><strong>Start the demo UUT</strong></div>"
            + html.mapping(config, caption="Configuration")
        )


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

    def as_html(self, label):
        name = html.text(label)
        return f"<span><strong>Snapshot the demo UUT</strong> as {name}.json</span>"
