from automationv3.framework.block import BuildingBlock, BlockResult

class Wait(BuildingBlock):

    def check_syntax(self, *args):
        return len(args) == 1

    def execute(self, seconds):
        time.sleep(seconds)
        return BlockResult(True)

    def as_rst(self, seconds):

        return f'.. raw:: html\n\n   <span><strong>Wait</strong> {seconds} seconds</span>\n\n'

