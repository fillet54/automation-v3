'''Models and utilites for reading and representing test cases'''

import docutils.core
from abc import ABC, abstractmethod

from . import edn
from .block import BuildingBlock, find_block
from .rst import extract_testcase_fields

# TODO: This likely should actually extend a job class.
#       TestCase will be only one type of job
class TestCase(ABC):
    '''Test case'''

    @property
    @abstractmethod
    def id(self):
        pass
    
    @property
    @abstractmethod
    def title(self):
        pass

    @property
    @abstractmethod
    def requirements(self):
        pass


class EdnTestCase(TestCase):
    '''Test case represented in edn

    An edn test case consist of a sequence of edn forms. The forms are 
    limited to the types of `edn.List` and `edn.String`. All other 
    forms are ignored/skipped.

    Forms of type `edn.List` are interpreted as representing building 
    blocks while forms of type `edn.String` are considered 
    documentation.

    Documentation is written in the reStructuredText(rst) format with 
    the entire testcase getting converted to a rst document for 
    interpretting and rendering. The various fields of the test case 
    are extracted the rst document. For example the title comes from 
    the title of the rst document and the requirements are extracted 
    from references 

    '''

    def __init__(self, id, text):
        self._id = id
        self.text = text

        self.fields = extract_testcase_fields(self.__repr_rst__())

    @property
    def id(self):
        return self._id
    
    @property
    def title(self):
        return self.fields['title']

    @property
    def requirements(self):
        return list(self.fields['requirements'])


    def __repr_rst__(self):
        return edn_to_rst(self.text)


def edn_to_rst(text):
    '''Convert edn forms to rst'''
    def form_to_rst(form):
        if isinstance(form, str):
            return form
        elif block := find_block(form):
            return block.__repr_rst__()

    rst = [form_to_rst(form)
           for form in edn.read_all(text)
           if isinstance(form, (str, list))]


    return '\n'.join(rst)

# The following will likely be moved to an rst.py module

if __name__ == '__main__':

    edn_sample = '''

"
=========
The Title
=========
"

(Wait 1)

'''

    tc = EdnTestCase('id1', edn_sample)

    print(tc.__repr_rst__())

    import docutils.core
    from .rst import TestCaseWriter 

    writer = TestCaseWriter()
    #writer.translator_class = TestcaseFieldsExtractor
    parts = docutils.core.publish_parts(tc.__repr_rst__(), writer=writer)
    print(parts)