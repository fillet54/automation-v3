'''Utilities for reStructuredText

'''

import docutils.core
from docutils import writers, nodes
from docutils.parsers.rst import roles, Directive, directives

from ..requirements.models import Requirement

#from docutils import nodes
#from docutils.nodes import TextElement, Inline, container, Text, SparseNodeVisitor
#from docutils.writers.html4css1 import Writer, HTMLTranslator
#
#from ..framework import edn
#
#ENDSTATEMENT_RST = '\n.. endstatement::\n\n'
#ENDSTATEMENT_DIV = '<splitter id="1234567890!!!!"/>'
#
#
def requirement_reference_role(role, rawtext, text, lineno, inliner, options=None, content=None):
    '''rst role to support software requirement references'''
    try:
        node = requirement(text)
        return [node], []
    except Exception as e:
        print(e)
    return [], []

class requirement(nodes.Inline, nodes.TextElement):
    def __init__(self, id):
        super().__init__()
        self.req = Requirement.find_by_id(id)
        if self.req is None:
            self.req = Requirement(id=id)


# Register requirement role 
roles.register_canonical_role('REQ', requirement_reference_role)

#class endstatement(Inline, TextElement):
#    pass
#
#class EndStatement(Directive):
#    '''This `Directive` will split up statements
#    '''
#    required_arguments = 0
#    optional_arguments = 0
#    has_content = False
#    def run(self):
#        thenode = endstatement()
#        return [thenode]
#
#
#class TestcaseHTMLTranslator(HTMLTranslator):
#    documenttag_args = {'tagname': 'div', 
#                        'CLASS': 'document prose prose-li:mt-0 prose-li:mb-0 prose-p:mb-1 prose-p:mt-1 prose-headings:mb-2 prose-headings:mt-5'}
#
#    # Delimiters for endstatement directives
#    ENDSTATEMENT_RST = '\n.. endstatement::\n\n'
#    ENDSTATEMENT_DIV = '<splitter id="1234567890!!!!"/>'
#    
#    def __init__(self, document):
#        HTMLTranslator.__init__(self, document)
#
#    def visit_document(self, node):
#        super().visit_document(node)
#        self.body.append(self.ENDSTATEMENT_DIV)
#
#    def depart_document(self, node):
#        self.body.append(self.ENDSTATEMENT_DIV)
#        super().depart_document(node)
#
#    # Don't want nested sections since we might split
#    # a section 
#    def visit_section(self, node): pass
#    def depart_section(self, node): pass
#
#    def visit_endstatement(self, node):
#        self.body.append(self.ENDSTATEMENT_DIV)
#        
#    def depart_endstatement(self, node): pass
#
#    def visit_requirement(self, node):
#        if self.requirement_by_id is not None:
#            req = self.requirement_by_id(node.req_id)
#            if req is not None:
#                return self.body.append(req.__repr_html__())
#            else:
#                return self.body.append(f'<div>{node.req_id}</div>')
#
#    def depart_requirement(self, node):
#        pass
#
#class TestcaseHTMLWriter(Writer):
#    def __init__(self, requirement_by_id=None):
#        Writer.__init__(self)
#
#        #class TestCaseHTMLTranslator(TestcaseHTMLTranslator):
#        #    '''
#        #    def __init__(self, *args, **kwargs):
#        #        super().__init__(*args, **kwargs)
#        #        self.requirement_by_id = requirement_by_id
#
#        self.translator_class = TestcaseHTMLTranslator







class TestCaseFieldWriter(writers.Writer):
    '''Writes test case fields to a dictionary'''
    def __init__(self):
        writers.Writer.__init__(self)
        self.translator_class = TestCaseTranslator
        self.visitor = None

    def translate(self):
        self.visitor = visitor = self.translator_class(self.document)
        self.document.walkabout(visitor)
        self.output = visitor.output


class TestCaseTranslator(nodes.GenericNodeVisitor):
    def __init__(self, document):
        nodes.NodeVisitor.__init__(self, document)
        self.output = {
            'title': '',
            'requirements': set()
        }

    # GenericNodeVisitor methods
    def default_visit(self, node):
        """Default node visit method."""
        pass

    def default_departure(self, node):
        """Default node depart method."""
        pass


    # NodeVisitor methods
    def unknown_departure(self, node):
        pass

    def unknown_visit(self, node):
        pass

    # Test case fields
    def visit_title(self, node):
        if isinstance(node.parent, nodes.document):
            self.output['title'] = node.astext()

    def visit_requirement(self, node):
        self.output['requirements'].add(node.req)


def extract_testcase_fields(text):
    '''Extracts testcase fields from reStructuredText'''
    writer = TestCaseFieldWriter()
    parts = docutils.core.publish_parts(text, writer=writer)
    return parts['whole']
