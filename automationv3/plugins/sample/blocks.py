"""Sample BuildingBlocks for the demo UUT"""

from automationv3.framework import context, edn, html
from automationv3.framework.block import BlockResult, BuildingBlock

MODE = edn.Keyword("mode")
READINGS = edn.Keyword("readings")


class StartDemo(BuildingBlock):
    """Restart the demo UUT from a configuration map::

        (StartDemo {:mode :emergency
                    :readings {:brake-pressure 70}})

    Values may use the script's definitions and variation symbols; the
    block gets them evaluated. In a rendered script the configuration
    reads as written, as a table.
    """

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
            stdout=f"started in {edn.writes(config[MODE]).strip()} "
                   f"with {len(readings)} reading(s)",
        )

    def as_html(self, config):
        return (
            "<div><strong>Start the demo UUT</strong></div>"
            + html.mapping(config, caption="Configuration")
        )
