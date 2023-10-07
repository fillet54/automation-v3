import io
import functools
import docutils.core
from docutils.nodes import TextElement, Inline, container, Text
from docutils.parsers.rst import Directive, directives, roles
from docutils.writers.html4css1 import Writer, HTMLTranslator

from ..framework import edn

ENDSTATEMENT_RST = '\n.. endstatement::\n\n'
ENDSTATEMENT_DIV = '<splitter id="1234567890!!!!"/>'


def requirement_reference_role(role, rawtext, text, lineno, inliner, options=None, content=None):
    try:
        node = requirement(text)
        return [node], []
    except Exception as e:
        print(e)
    return [], []

class endstatement(Inline, TextElement):
    pass

class requirement(Inline, TextElement):
    def __init__(self, id):
        super().__init__()
        self.req_id = id

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

    def visit_requirement(self, node):
        if self.requirement_by_id is not None:
            req = self.requirement_by_id(node.req_id)
            if req is not None:
                return self.body.append(req.__repr_html__())
            else:
                return self.body.append(f'<div>{node.req_id}</div>')

    def depart_requirement(self, node):
        pass

class TestcaseHTMLWriter(Writer):
    def __init__(self, requirement_by_id=None):
        Writer.__init__(self)

        # Got to be a better way
        class MyHTMLTranslator(TestcaseHTMLTranslator):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.requirement_by_id = requirement_by_id

        self.translator_class = MyHTMLTranslator
        #self.translator_class = lambda *args, **kwargs: TestcaseHTMLTranslator(*args, requirement_by_id=requirement_by_id, **kwargs)

#register directives and roles
directives.register_directive('endstatement', EndStatement)
roles.register_canonical_role('REQ', requirement_reference_role)

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

def edn_writes(stmt, indent=0):
    try:
        s = edn.writes(stmt).strip()
        prefix = ' ' * indent
        return ''.join(f'{prefix}{line}\n' for line in s.splitlines()).strip('\n')
    except Exception as e:
        print(e)

def if_special_form_html(stmt):
    body = f'''\
<strong class="text-white">{stmt[0]}:</strong>\n<span class="text-blue-500">{edn_writes(stmt[1], 2)}</span>
<strong class="text-white">then:</strong>\n{edn_writes(stmt[2], 2)}'''

    if len(stmt) == 4:
        body += '\n<strong class="text-white">else:\n  ' + edn_writes(stmt[3], 2)

    return f"<pre>{body}</pre>"

def startsimulation_html(stmt):
    body = f'''<strong class="text-white">StartSimuation</strong>\n'''
    pairs = [(edn.writes(k).strip(), edn.writes(v).strip())
             for k,v in zip(stmt[1::2], stmt[2::2])]

    max_k_len = max(len(k) for k,v in pairs)
    
    for k,v in pairs:
        body += '   ' + k + ' '*(max_k_len - len(k)) + ' ' + v + '\n'

    return f"<pre>{body}</pre>"

def tabledriven_html(stmt):
    _, headers, rows = stmt

    s = io.StringIO('')
    s.write('<div class="-mx-4 -my-2 overflow-x-auto sm:-mx-6 lg:-mx-8">')
    s.write('<div class="inline-block min-w-full py-2 align-middle sm:px-6 lg:px-8">')
    s.write('<div class="overflow-hidden shadow ring-1 ring-black ring-opacity-5 sm:rounded-lg">')
    s.write('<table class="my-0 min-w-full divide-y divide-gray-300">')
    s.write('<thead class="bg-gray-50"><tr class="divide-x divide-gray-200">')
    s.write('\n'.join(f'<td class="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">{header}</td>' for header in headers))
    s.write('</tr></thead>')
    s.write('<tbody>')
    for row in rows:
        s.write('<tr class="divide-x divide-gray-200">')
        s.write(''.join(f'<td class="whitespace-nowrap py-4 pl-4 pr-3 text-sm font-medium text-gray-900 sm:pl-6">{data}</td>' for data in row))
        s.write('</tr>')
    s.write('</tbody>')
    s.write('</table>')
    s.write('</div>')
    s.write('</div>')
    s.write('</div>')

    return s.getvalue()


html_repr = {
    #'if': if_special_form_html,
    'if-not': if_special_form_html,
    'StartSimulation': startsimulation_html,
    'Table-Driven': tabledriven_html
}

class Statement:

    def __init__(self, statement, html=None, rst=None):
        self.statement = statement
        self.html = html or ''
        self.rst = rst or ''


        # TODO: This is just for quick examples
        # special lookups
        if len(statement) > 0 and statement[0] in html_repr:
            self.html = html_repr[statement[0]](statement)
        

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
            # turn escaped newlines to actual newlines and remove whitespace
            text = text.replace('\\n', '\n').strip()
            #strip off quotes
            text = text.strip('"')
            # strip any other whitespace
            text = text.strip()
            # add back in quotes
            text = f'"\n{text}\n"'
            
            ## newlines as real newlines
            #text = text.replace('\\n', '\n')
            ## leading and trailing double-quote on ownline
            #if not text.startswith('"\n'):
            #    text = f'"\n{text[1:]}'
            #if not text.endswith('\n"'):
            #    text = f'{text[:-1]}\n"'
        return text + '\n'


# Basic caching of text content to Testcase statements
# This improves performance quite a bit as usually from
# the webside there is a request for EACH statement which
# required reparsing everything. Now we only reparse on
# change of text content
@functools.lru_cache(maxsize=128)
def get_statements(content, requirement_by_id=None):
    statements = read_edn_statements(content)
    
    # At this point we can assume all of our statements
    # are in rst format. To allow us to split up the rendered
    # html we need to insert some marker so we can split on
    # that after. To do this we will use a custom rst
    # directive.
    rst_statements = [_repr_rst_(stmt)
                      for stmt in statements]
    html = docutils.core.publish_parts(ENDSTATEMENT_RST.join(rst_statements),
                                       writer=TestcaseHTMLWriter(requirement_by_id),
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

## This should be moved to the editor. The rest above is probably useful within the framework
class Testcase:

    def __init__(self, document, requirement_by_id=None):
        self.document = document
        self.requirement_by_id = requirement_by_id

    @property
    def statements(self):
        # Always return a copy so the cache doesnt get messed up
        return list(get_statements(self.document.content, self.requirement_by_id))

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
        original_len = len(all_statements)

        if index != -1:
            all_statements[index:index+1] = statements
        else:
            all_statements += statements
            

        # Now we need to just write out each sections
        content = '\n'.join([stmt._repr_edn_()
                             for stmt in all_statements])
        self.document.save_draft(content)

        # Still not sure how I handle this.
        # return the sections updated
        # if statements read is of len == 1 then its only this index
        # otherwise its current index until the end
        if index == -1: # added at end
            modified = list(range(original_len, original_len+len(statements)))
            shifted = []
        elif len(statements) <= 1:
            modified = [index]
            shifted = []
        else:
            modified = [i for i in range(index, index+len(statements))] 
            shifted = [(i, i+len(statements)-1)
                       for i in range(index+1, original_len)]

        return modified, shifted
