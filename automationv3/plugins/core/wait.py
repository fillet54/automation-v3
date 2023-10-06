from automationv3.framework.block import BuildingBlock, BlockResult

class Wait(BuildingBlock):

    def execute(self, seconds):
        time.sleep(seconds)
        return BlockResult(True)

