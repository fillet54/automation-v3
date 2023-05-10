
import unittest
import os

from automationv3.framework.edn import read, writes, Symbol, Keyword, List, Vector, Map, Set


class TestEdnWriter(unittest.TestCase):

    # Symbols
    def test_symbol_basic(self):
        self.assertEqual('abc', writes(Symbol('abc')))

    def test_symbol_with_namespace(self):
        self.assertEqual('ns/my-name', writes(Symbol('my-name', namespace='ns')))

    def test_symbol_true(self):
        self.assertEqual('true', writes(True))
    
    def test_symbol_false(self):
        self.assertEqual('false', writes(False))

    def test_symbol_nil(self):
        self.assertEqual('nil', writes(None))

    def test_symbol_single_slash(self):
        self.assertEqual('/', writes(Symbol('/')))
    
    def test_symbol_namespace_single_slash(self):
        self.assertEqual('ns//', writes(Symbol('/', namespace='ns')))

    # Strings
    def test_string_basic(self):
        self.assertEqual('"abc"', writes('abc'))
    
    def test_string_empty(self):
        self.assertEqual('""', writes(''))

    def test_string_char_escapes(self):
        self.assertEqual(r'"\t\r\n\\\"\b\f"', writes('\t\r\n\\"\b\f'))

    # Chars
    # TODO: Round-trip characters 
    
    # Keywords
    def test_keyword_basic(self):
        self.assertEqual(':abc', writes(Keyword('abc')))

    def test_keyword_with_ns(self):
        self.assertEqual(':ns/abc', writes(Keyword('abc', namespace='ns')))

    # Integers
    def test_integer_basic(self):
        self.assertEqual('0', writes(0))
        self.assertEqual('42', writes(42))
        
    def test_integer_signed(self):
        self.assertEqual('-42', writes(-42))

    # TODO: Maintain round trip octal/hex
    # TODO: Round-trip radix 

    # Floating Point
    def test_float_basic(self):
        self.assertEqual('34.1', writes(34.1))

    # TODO: Round-trip scientific notation
    # TODO: Round-trip ratio

    # List
    def test_list_basic(self):
        self.assertEqual('(1 2 3)', writes(read('(1 2 3)')))
    
    def test_list_with_complex_will_indent_each(self):
        self.assertEqual('''\
(
  (1 2)
  3
)''', writes(read('((1 2) 3)')))

    # TODO: Round-trip user style. 
    # We can possibly use meta data to figure out
    # if the original list spanned multiple lines or not

    # Vector
    def test_vector_basic(self):
        self.assertEqual('[1 2 3]', writes(read('[1 2 3]')))
    
    def test_vector_with_complex_will_indent_each(self):
        self.assertEqual('''\
[
  (1 2)
  3
]''', writes(read('[(1 2) 3]')))

    # Map 
    def test_map_basic(self):
        self.assertEqual('{:a 1 :b 2 :c 3}', writes(read('{:a 1 :b 2 :c 3}')))
    
    def test_vector_with_complex_will_indent_each(self):
        self.assertEqual('''\
{
  :a (1 2)
  :b 2
  :c 3
}''', writes(read('{:a (1 2) :b 2 :c 3}')))


    # Set 
    def test_set_basic(self):
        self.assertEqual('#{1 2 3}', writes(read('#{1 2 3}')))
    
    def test_set_with_complex_will_indent_each(self):
        self.assertEqual('''\
#{
  3
  (1 2)
}''', writes(read('#{(1 2) 3}')))

    # TODO: maintain set order


    # TODO: Quote shorthand
