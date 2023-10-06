
class BuildingBlock:
    ''' 
    The 'BuildingBlock' of the automation framework. Registers as a function to
    be run during text execution.
    '''
    def name(self):
        '''Returns the name of the building block. The name is used
        as a first order lookup for the block'''
        return type(self).__name__
    
    def check_syntax(self, *args):
        '''Returns True if this BuildingBlock can support the 
        arguments and False otherwise'''
        return True
    
    def execute(self, *args):
        '''Executes the block. 

        Returns a BlockResult'''
        return BlockResult(False)


class BlockResult(object):
    '''
    The result of executing a BuildingBlock
    '''
    def __init__(self, passed, stdout="", stderr=""):
        self.passed = passed
        self.stdout = stdout
        self.stderr = stderr
        
    def __bool__(self):
        return self.passed
    
    def __str__(self):
        result = 'PASS' if self.passed else 'FAIL'
        return f'<BlockResult: {result}, {self.stdout}, {self.stderr}>'
