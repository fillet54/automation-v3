import functools
import docutils.core
from docutils.nodes import TextElement, Inline
from docutils.parsers.rst import Directive, directives
from docutils.writers.html4css1 import Writer, HTMLTranslator

from ..framework import edn

ENDSTATEMENT_RST = '\n.. endstatement::\n\n'
ENDSTATEMENT_DIV = '<splitter id="1234567890!!!!"/>'

class endstatement(Inline, TextElement):
    pass

class EndStatement(Directive):
    '''This `Directive` will split up statements
    '''
    required_arguments = 0
    optional_arguments = 0
    has_content = False
    def run(self):
        thenode = endstatement()
        return [thenode]

class TestcaseHTMLTranslator(HTMLTranslator):
    documenttag_args = {'tagname': 'div', 
                        'CLASS': 'document prose prose-li:mt-0 prose-li:mb-0 prose-p:mb-1 prose-p:mt-1 prose-headings:mb-2 prose-headings:mt-5'}
    
    def __init__(self, document):
        HTMLTranslator.__init__(self, document)

    def visit_document(self, node):
        super().visit_document(node)
        self.body.append(ENDSTATEMENT_DIV)

    def depart_document(self, node):
        self.body.append(ENDSTATEMENT_DIV)
        super().depart_document(node)

    # Don't want nested sections since we might split
    # a section 
    def visit_section(self, node): pass
    def depart_section(self, node): pass

    def visit_endstatement(self, node):
        self.body.append(ENDSTATEMENT_DIV)
        
    def depart_endstatement(self, node): pass

class TestcaseHTMLWriter(Writer):
    def __init__(self):
        Writer.__init__(self)
        self.translator_class = TestcaseHTMLTranslator

#register directive
directives.register_directive('endstatement', EndStatement)

def rst_codeblock(src):
    return '\n'.join([
        '.. code-block:: clojure',
        '',
        *['  '+line for line in src.splitlines()]  
    ]) + '\n\n'


def read_edn_statements(src):
    stream = edn.PushBackCharStream(src)
    statements = []
    while len(statements) == 0 or statements[-1] != edn.READ_EOF:
        statement = edn.read(stream)
        statements.append(statement)
    statements.pop()  # don't need EOF
    return statements
  
def _repr_rst_(obj):
    '''Convert object to RST'''
    if isinstance(obj, str):
        return obj
    else:
        return rst_codeblock(edn.writes(obj))

class Statement:

    def __init__(self, statement, html=None, rst=None):
        self.statement = statement
        self.html = html or ''
        self.rst = rst or ''

    def __str__(self):
        return edn.writes(self.statement).replace('\\n', '\n').strip('"')

    def __repr__(self):
        return str(self)

    def _repr_html_(self):
        return self.html

    def _repr_rst_(self):
        return self.rst

    def _repr_edn_(self):
        text = edn.writes(self.statement).strip()

        # Clean up string formatting. This should
        # always be raw RST so just clean it up for
        # consistency in the edn file
        if isinstance(self.statement, str):
            # newlines as real newlines
            text = text.replace('\\n', '\n')
            # leading and trailing double-quote on ownline
            if not text.startswith('"\n'):
                text = f'"\n{text[1:]}'
            if not text.endswith('\n"'):
                text = f'{text[:-1]}\n"'
        return text + '\n'


# Basic caching of text content to Testcase statements
# This improves performance quite a bit as usually from
# the webside there is a request for EACH statement which
# required reparsing everything. Now we only reparse on
# change of text content
@functools.lru_cache(maxsize=128)
def get_statements(content):
    statements = read_edn_statements(content)
    
    # At this point we can assume all of our statements
    # are in rst format. To allow us to split up the rendered
    # html we need to insert some marker so we can split on
    # that after. To do this we will use a custom rst
    # directive.
    rst_statements = [_repr_rst_(stmt)
                      for stmt in statements]
    html = docutils.core.publish_parts(ENDSTATEMENT_RST.join(rst_statements),
                                       writer=TestcaseHTMLWriter(),
                                       settings_overrides={'initial_header_level':'3'})
    
    # Now we should be able to split the HTML on
    # our custom div pattern. Throw away the first
    # and last as thats the wrapping 'document' divs 
    html_statements = html['html_body'].split(ENDSTATEMENT_DIV)[1:-1]
    
    # Wrap our statements
    statements = [Statement(stmt, html, rst)
                  for stmt, html, rst in zip(statements,
                                        html_statements,
                                        rst_statements)]
    
    return statements


class Testcase:

    def __init__(self, document):
        self.document = document

    @property
    def statements(self):
        # Always return a copy so the cache doesnt get messed up
        return list(get_statements(self.document.content))

    def update_statement(self, index, value):
        # simple detection of rst or code
        # very rare should a rst step start with a (
        # otherwise need to have the GUI handle cell
        # types

        if not value.strip().startswith('('):
            value = f'"{value}"'

        statements = [Statement(stmt)
                      for stmt in read_edn_statements(value)]

        all_statements = self.statements
        all_statements[index:index+1] = statements

        # Now we need to just write out each sections
        content = '\n'.join([stmt._repr_edn_()
                             for stmt in all_statements])
        self.document.save_draft(content)

        # Still not sure how I handle this.
        # return the sections updated
        # if statements read is of len == 1 then its only this index
        # otherwise its current index until the end
        if len(statements) <= 1:
            return [index]
        else:
            return list(range(index, len(all_statements)))

