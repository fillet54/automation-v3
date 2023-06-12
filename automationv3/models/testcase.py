'''This model represents a test case'''
import textwrap

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

        name, section_text = part.split(maxsplit=1)
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
SETUP = edn.Keyword('setup', namespace='rvt')

class Testcase:
    def __init__(self, document):
        self.document = document
        self._map, self._errors = read_testcase(document.content)

    def save(self):
        '''Saves a testcase out to an edn'''

        # To maintain styling we will write out each section

        lines = ['{']
        lines.append(f'{repr(TITLE)} {edn.writes(self._map[TITLE])}')

        lines.append(f'{repr(DESC)}')
        lines.append(edn.writes(self._map[DESC]).replace('\\n', '\n'))

        lines.append(f'{repr(REQS)} {edn.writes(self._map[REQS])}')
        lines.append(f'{repr(SETUP)} {edn.writes(self._map[SETUP])}')
        lines.append(f':rvt/preconditions {edn.writes([])}')
        lines.append(f':rvt/steps {edn.writes("")}')

        lines.append('}')

        self.document.save_draft('\n'.join(lines))
    
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
    
    @requirements.setter
    def requirements(self, value):
        self._map[REQS] = value
        self.save()

    @property
    def setup(self):
        return self._map[SETUP]
    
    @setup.setter
    def setup(self, value):
        self._map[SETUP] = value
        self.save()

    @property
    def errors(self):
        return self._errors

