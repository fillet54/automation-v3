from automationv3.framework.block import BuildingBlock, BlockResult
from automationv3.framework import edn, html


class Wait(BuildingBlock):
    def check_syntax(self, *args):
        return len(args) == 1

    def execute(self, seconds):
        return BlockResult(True)

    def as_html(self, seconds):
        return f"<span><strong>Wait</strong> {seconds} seconds</span>"


class SetupSimulation(BuildingBlock):
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
    def name(self):
        return "Table-Driven"

    # Headers are bare symbols naming columns, not values to evaluate
    def execute_forms(self, *args):
        return BlockResult(True)

    def as_html(self, *args):
        headers, rows = args
        return html.table([str(h) for h in headers], rows)
