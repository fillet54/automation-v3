'''This model represents a test case'''
from ..framework import edn


def read_testcase(stream_or_str, sentinel=None):
    '''Specialized reader for handling testcases that will be
       rendered in a UI. This requires special handling to allow
       partially written documents to be properly rendered so that
       errors can be fixed.

       The basic idea is that we will first treat each section of
       the testcase on their own. We can assume a testcase is a 
       map with keys in the 'rvt' namespace. For each section
       we can attempt to read a single form and if success then
       we are done otherwise depending on the key we will do special
       processing to arrive at content
    '''

    if isinstance(stream_or_str, str):
        text = stream_or_str 
    else:
        text = ''.join(stream_or_str)

    # Simplest way I can think of is to just assume the 'rvt' namespace
    # will not be used in the document contents. We can revisit if this 
    # is not the case in practice
    text = text.strip()
    if text[0] != '{' or text[-1] != '}':
        raise Exception("Invalid Testcase")
    text = text[1:-1]
    parts = text.split(':rvt/')

    testcase = {
    }
    errors = []

    for part in parts:
        if part.strip() == '':
            continue

        name, section_text = part.split(' ', maxsplit=1)
        fqname = edn.Keyword(name, namespace='rvt')
        try:
            # TODO: Maintain lineinfo metadata
            section_content = edn.read(section_text)
            testcase[fqname] = section_content
        except Exception:
            testcase[fqname] = section_text
            errors.append(name)

    return testcase, errors


TITLE = edn.Keyword('title', namespace='rvt')
DESC = edn.Keyword('description', namespace='rvt')
REQS = edn.Keyword('requirements', namespace='rvt')

class Testcase:
    def __init__(self, document):
        self.document = document
        self._map, self._errors = read_testcase(document.content)

    def save(self):
        self.document.save_draft(edn.writes(self._map))
    
    @property
    def title(self):
        return self._map[TITLE]

    @title.setter
    def title(self, value):
        if self._map[TITLE] == str(value).strip():
            return
        self._map[TITLE] = str(value).strip()
        self.save()

    @property
    def description(self):
        return self._map[DESC]
    
    @description.setter
    def description(self, value):
        if self._map[DESC] == str(value).strip():
            return
        self._map[DESC] = str(value).strip()
        self.save()

    @property
    def requirements(self):
        return self._map[REQS]

    @property
    def errors(self):
        return self._errors
