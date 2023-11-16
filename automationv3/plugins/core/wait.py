from automationv3.framework.block import BuildingBlock, BlockResult
from automationv3.framework import edn

class Wait(BuildingBlock):

    def check_syntax(self, *args):
        return len(args) == 1

    def execute(self, seconds):
        time.sleep(seconds)
        return BlockResult(True)

    def as_rst(self, seconds):

        return f'.. raw:: html\n\n   <span><strong>Wait</strong> {seconds} seconds</span>\n\n'

class SetupSimulation(BuildingBlock):

    def check_syntax(self, *args):
        return (len(args) % 2) == 0

    def execute(self, *arg):
        return BlockResult(True)

    def as_rst(self, *args):
        lines = ['.. code-block:: clojure',
                 '', 
                 '   (SetupSimulation']
        # TODO: Clean this up
        for arg1, arg2 in zip(args[::2], args[1::2]):
            if isinstance(arg1, str) and not isinstance(arg1, (edn.Symbol, edn.Keyword)):
                arg1 = f'"{arg1}"'
            if isinstance(arg2, str) and not isinstance(arg2, (edn.Symbol, edn.Keyword)):
                arg2 = f'"{arg2}"'
            lines.append(f'      {arg1} {arg2}')
        lines[-1] += ')\n\n'
        
        return '\n'.join(lines) 

