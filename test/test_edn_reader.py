import unittest
import os

from automationv3.framework.edn import read, Symbol, Keyword, List, Vector, Map, Set


class TestEdnReader(unittest.TestCase):

    # Symbols
    def test_symbol_basic(self):
        self.assertEqual(read('abc'), Symbol('abc'))

    def test_symbol_with_namespace(self):
        self.assertEqual(read('ns/my-name'), Symbol('my-name', namespace='ns'))

    def test_symbol_true(self):
        self.assertEqual(read('true'), True)
    
    def test_symbol_false(self):
        self.assertEqual(read('false'), False)

    def test_symbol_nil(self):
        self.assertEqual(read('nil'), None)

    def test_symbol_single_slash(self):
        self.assertEqual(read('/'), Symbol('/'))
    
    def test_symbol_namespace_single_slash(self):
        self.assertEqual(read('ns//'), Symbol('/', namespace='ns'))

    def test_symbol_cannot_have_trailing_colon(self):
        with self.assertRaises(Exception) as c:
            read('invalid:')
    
    def test_symbol_can_only_have_a_single_slash(self):
        with self.assertRaises(Exception) as c:
            read('ns/double/slash')

    # Strings
    def test_string_basic(self):
        self.assertEqual(read('"abc"'), 'abc')
    
    def test_string_empty(self):
        self.assertEqual(read('""'), '')

    def test_string_char_escapes(self):
        self.assertEqual(read(r'"\t\r\n\\\"\b\f"'), '\t\r\n\\"\b\f')
    
    def test_string_hex_unicode(self):
        self.assertEqual(read(r'"\u0021"'), '!')
    
    def test_string_octal_unicode(self):
        self.assertEqual(read(r'"\041"'), '!')

    def test_string_EOF_String(self):
        with self.assertRaises(Exception) as c:
            read('"abc')
    
    def test_string_invalid_escape(self):
        with self.assertRaises(Exception) as c:
            read(r'"\ "')
    
    def test_string_hex_unicode_cannot_have_invalid_hex_digit(self):
        with self.assertRaises(Exception) as c:
            read(r'"\u123G"')
    
    def test_string_octal_unicode_cannot_have_invalid_octal_digit(self):
        with self.assertRaises(Exception) as c:
            read(r'"\128"')

    # Characters
    def test_char_basic(self):
        self.assertEqual(read(r'\c'), 'c')

    def test_char_keyword_newline(self):
        self.assertEqual(read(r'\newline'), '\n')
    
    def test_char_keyword_space(self):
        self.assertEqual(read(r'\space'), ' ')

    def test_char_keyword_tab(self):
        self.assertEqual(read(r'\tab'), '\t')
    
    def test_char_keyword_backspace(self):
        self.assertEqual(read(r'\backspace'), '\b')

    def test_char_keyword_formfeed(self):
        self.assertEqual(read(r'\formfeed'), '\f')

    def test_char_keyword_return(self):
        self.assertEqual(read(r'\return'), '\r')
    
    def test_char_unicode_hex_escapes(self):
        self.assertEqual(read(r'\u0021'), '!')

    def test_char_unicode_octal_escapes(self):
        self.assertEqual(read(r'\o41'), '!')

    def test_char_ending_brackets_can_be_escaped(self):
        self.assertEqual(read(r'\]'), ']')
        self.assertEqual(read(r'\['), '[')
    
    def test_char_ending_parens_can_be_escaped(self):
        self.assertEqual(read(r'\('), '(')
        self.assertEqual(read(r'\)'), ')')

    def test_char_keyword_unknown(self):
        with self.assertRaises(Exception) as c:
            read(r'\unknown')
    
    def test_char_cannot_have_just_backslash(self):
        with self.assertRaises(Exception) as c:
            read(r'\ ')

    # Keywords
    def test_keyword_basic(self):
        self.assertEqual(read(':abc'), Keyword('abc'))

    def test_keyword_with_ns(self):
        self.assertEqual(read(':ns/abc'), Keyword('abc', namespace='ns'))

    def test_keyword_single_colon_not_allowed(self):
        with self.assertRaises(Exception) as c:
            read(r':')
    
    def test_keyword_alias_namespace_not_supported(self):
        with self.assertRaises(Exception) as c:
            read(r'::alias/my-keyword')

    # Integers
    def test_integer_basic(self):
        self.assertEqual(read(r'0'), 0)
        self.assertEqual(read(r'42'), 42)
        
    def test_integer_signed(self):
        self.assertEqual(read(r'+0'), 0)
        self.assertEqual(read(r'-0'), 0)
        self.assertEqual(read(r'-42'), -42)

    def test_integer_octal(self):
        self.assertEqual(read(r'052'), 42)

    def test_integer_other_radix(self):
        self.assertEqual(read(r'8r52'), 42)
        self.assertEqual(read(r'16r2a'), 42)
        self.assertEqual(read(r'36r16'), 42)
        self.assertEqual(read(r'2r101010'), 42)

    # Floating Point
    def test_float_basic(self):
        self.assertEqual(read(r'34.1'), 34.1)
    
    def test_float_scientific_notation(self):
        self.assertEqual(read(r'3e5'), 3e5)

    def test_float_ratios(self):
        self.assertEqual(read(r'1/2'), 0.5)

    # List
    def test_list_basic(self):
        self.assertEqual(read(r'(1 2 3)'), [1, 2, 3])
        self.assertEqual(type(read(r'(1 2 3)')), List)

    # Vector 
    def test_vector_basic(self):
        self.assertEqual(read(r'[1 2 3]'), [1, 2, 3])
        self.assertEqual(type(read(r'[1 2 3]')), Vector)

    # Map 
    def test_map_basic(self):
        self.assertEqual(read(r'{:a 1 :b 2 :c 3}'), {'a':1, 'b':2, 'c':3})
        self.assertEqual(type(read(r'{:a 1 :b 2 :c 3}')), Map)

    # Set 
    def test_set_basic(self):
        self.assertEqual(read(r'#{1 2 5 5 1 3 4 4}'), {1, 2, 3, 4, 5})
        self.assertEqual(type(read(r'#{1 2 5 5 1 3 4 4}')), Set)

    # Comments
    def test_comment_basic(self):
        self.assertEqual(read(r'''[
        1 ; first entry
        2 ; second entry
    ]'''), [1, 2])
    
    # Quote
    def test_quote_shorthand(self):
        self.assertEqual(read(r"'(1 2 3)"), ['quote', [1, 2, 3]])

if __name__ == '__main__':
    unittest.main()
