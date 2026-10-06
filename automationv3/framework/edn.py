"""Reading and writing edn, the data notation scripts are written in

`read` and `read_all` turn edn text into Python values: lists become
List, vectors Vector, maps Map, sets Set, symbols Symbol and keywords
Keyword; strings and characters become str, numbers int or float, and
true, false and nil become True, False and None. `writes` turns values
back into edn text, laying out large collections over several lines.

Tagged elements (#inst ...), metadata and discards (#_) are not
supported. See https://github.com/edn-format/edn.
"""

import re


class ParseError(ValueError):
    """Unreadable edn, and where (0-based line and column)"""

    def __init__(self, message, line, col):
        super().__init__(f"{message} (line: {line}, col: {col})")
        self.line = line
        self.col = col


# Values


class Symbol(str):
    """A name, optionally qualified by a namespace (ns/name).

    A symbol equals the string of its qualified name, so it can be
    looked up in, or compared with, plain strings.
    """

    def __new__(cls, name, namespace=None):
        symbol = super().__new__(cls, name)
        symbol.namespace = namespace
        return symbol

    @property
    def qualified(self):
        name = str.__str__(self)
        return f"{self.namespace}/{name}" if self.namespace else name

    def __eq__(self, other):
        if isinstance(other, type(self)):
            return str.__eq__(self, other) and self.namespace == other.namespace
        if isinstance(other, str):
            return self.qualified == str.__str__(other)
        return NotImplemented

    def __ne__(self, other):
        equal = self.__eq__(other)
        return equal if equal is NotImplemented else not equal

    def __hash__(self):
        return hash(str(self))

    def __str__(self):
        return self.qualified

    __repr__ = __str__


class Keyword(Symbol):
    """:name or :ns/name"""

    def __str__(self):
        return ":" + self.qualified

    __repr__ = __str__


class List(list):
    def __hash__(self):
        return hash(tuple(self))


class Vector(list):
    pass


class Map(dict):
    pass


class Set(set):
    pass


# Reading

WHITESPACE = " \t\r\n,"
DELIMITERS = '";@^`()[]{}\\'  # end a token
CLOSERS = ")]}"

STRING_ESCAPES = {"t": "\t", "r": "\r", "n": "\n", "\\": "\\", '"': '"',
                  "b": "\b", "f": "\f"}
NAMED_CHARS = {"newline": "\n", "space": " ", "tab": "\t", "backspace": "\b",
               "formfeed": "\f", "return": "\r"}
OCTAL = "01234567"
HEX = "0123456789abcdefABCDEF"

INT = re.compile(
    r"([-+]?)(?:(0)|([1-9][0-9]*)|0[xX]([0-9A-Fa-f]+)|0([0-7]+)"
    r"|([1-9][0-9]?)[rR]([0-9A-Za-z]+))N?")
FLOAT = re.compile(r"([-+]?[0-9]+(\.[0-9]*)?([eE][-+]?[0-9]+)?)M?")
RATIO = re.compile(r"([-+]?[0-9]+)/([0-9]+)")
BAD_OCTAL = re.compile(r"[-+]?0[0-9]+N?")  # e.g. 08: not octal, not decimal

# What reading a form can give instead of a form
_EOF = object()
_CLOSED = object()  # the closing delimiter of the collection being read


class _Reader:
    """Characters of the text being read, one at a time"""

    def __init__(self, text):
        self.text = text
        self.pos = 0

    def peek(self):
        return self.text[self.pos] if self.pos < len(self.text) else None

    def next(self):
        ch = self.peek()
        if ch is not None:
            self.pos += 1
        return ch

    def token(self, first):
        """`first` and the characters after it up to a delimiter"""
        start = self.pos - len(first)
        while (ch := self.peek()) is not None and ch not in WHITESPACE + DELIMITERS:
            self.pos += 1
        return self.text[start:self.pos]

    def error(self, message):
        line = self.text.count("\n", 0, self.pos)
        col = self.pos - (self.text.rfind("\n", 0, self.pos) + 1)
        return ParseError(message, line, col)


def read(text):
    """The first form in `text`"""
    reader = _Reader(text)
    form = _read_form(reader)
    if form is _EOF:
        raise reader.error("No form to read")
    return form


def read_all(text):
    """Every form in `text`, in order"""
    reader = _Reader(text)
    forms = []
    while (form := _read_form(reader)) is not _EOF:
        forms.append(form)
    return forms


def _read_form(reader, closer=None):
    """The next form, _CLOSED at `closer`, or _EOF at the end of the text"""
    while True:
        ch = reader.next()
        if ch is None:
            return _EOF
        if ch in WHITESPACE:
            continue
        if ch == ";":  # a comment, to the end of the line
            while reader.next() not in ("\n", None):
                pass
            continue
        if ch == closer:
            return _CLOSED
        if ch in CLOSERS:
            raise reader.error(f"Unexpected '{ch}'")
        if ch.isdigit() or (ch in "+-" and (reader.peek() or "").isdigit()):
            return _read_number(reader, ch)
        if ch in _MACROS:
            return _MACROS[ch](reader)
        return _read_symbol(reader, ch)


def _read_collection(reader, closer):
    forms = []
    while (form := _read_form(reader, closer)) is not _CLOSED:
        if form is _EOF:
            raise reader.error(f"Missing closing '{closer}'")
        forms.append(form)
    return forms


def _read_list(reader):
    return List(_read_collection(reader, ")"))


def _read_vector(reader):
    return Vector(_read_collection(reader, "]"))


def _read_map(reader):
    forms = _read_collection(reader, "}")
    if len(forms) % 2:
        raise reader.error("Map must have value for every key")
    return Map(zip(forms[::2], forms[1::2]))


def _read_dispatch(reader):
    if reader.next() == "{":
        return Set(_read_collection(reader, "}"))
    raise reader.error("Only #{...} sets are supported after #")


def _read_quote(reader):
    form = _read_form(reader)
    if form is _EOF:
        raise reader.error("Nothing to quote")
    return List([Symbol("quote"), form])


def _read_string(reader):
    chars = []
    while (ch := reader.next()) != '"':
        if ch is None:
            raise reader.error("EOF in middle of string")
        chars.append(_read_escape(reader) if ch == "\\" else ch)
    return "".join(chars)


def _read_escape(reader):
    ch = reader.next()
    if ch in STRING_ESCAPES:
        return STRING_ESCAPES[ch]
    if ch == "u":
        return _code_point(reader, _take(reader, 4), 16)
    if ch is not None and ch.isdigit():
        return _code_point(reader, ch + _take(reader, 2), 8)
    raise reader.error(f"Invalid escape '\\{ch}'")


def _take(reader, n):
    """The next `n` characters, or fewer at the end of the text"""
    return "".join(reader.next() or "" for _ in range(n))


def _code_point(reader, digits, base):
    allowed = HEX if base == 16 else OCTAL
    if not digits or any(d not in allowed for d in digits):
        raise reader.error(f"Invalid unicode escape '{digits}'")
    return chr(int(digits, base))


def _read_char(reader):
    ch = reader.next()
    if ch is None:
        raise reader.error("EOF in character")
    if ch in WHITESPACE:
        raise reader.error("Backslash cannot be followed by whitespace")
    token = ch if ch in DELIMITERS else reader.token(ch)
    if len(token) == 1:
        return token
    if token in NAMED_CHARS:
        return NAMED_CHARS[token]
    if token[0] == "u" and len(token) == 5:
        return _code_point(reader, token[1:], 16)
    if token[0] == "o":
        return _code_point(reader, token[1:], 8)
    raise reader.error(f"Invalid character escape '{token}'")


def _read_keyword(reader):
    ch = reader.next()
    if ch is None or ch in WHITESPACE:
        raise reader.error("Single colon not allowed")
    namespace, name = _split_symbol(reader, reader.token(ch))
    if namespace is not None and namespace.startswith(":"):
        raise reader.error("Namespace alias not supported")
    return Keyword(name, namespace)


def _read_symbol(reader, ch):
    token = reader.token(ch)
    if token in ("nil", "true", "false"):
        return {"nil": None, "true": True, "false": False}[token]
    namespace, name = _split_symbol(reader, token)
    return Symbol(name, namespace)


def _split_symbol(reader, token):
    """(namespace, name) of a symbol or keyword's token"""
    invalid = reader.error(f"Invalid symbol: '{token}'")
    if token.startswith("::") or token.endswith(":"):
        raise invalid
    if token == "/" or "/" not in token:
        return None, token
    namespace, name = token.split("/", 1)
    if (not name or name[0].isdigit() or namespace.endswith(":")
            or (name != "/" and "/" in name)):
        raise invalid
    return namespace, name


def _read_number(reader, ch):
    token = reader.token(ch)
    if BAD_OCTAL.fullmatch(token) and not INT.fullmatch(token):
        raise reader.error(f"Invalid octal number '{token}'")
    if m := INT.fullmatch(token):
        sign, zero, decimal, hexadecimal, octal, radix, digits = m.groups()
        if zero:
            return 0
        if decimal:
            value = int(decimal)
        elif hexadecimal:
            value = int(hexadecimal, 16)
        elif octal:
            value = int(octal, 8)
        else:
            value = int(digits, int(radix))
        return -value if sign == "-" else value
    if m := FLOAT.fullmatch(token):
        return float(m.group(1))  # M (exact) is read as a float too
    if m := RATIO.fullmatch(token):
        return int(m.group(1)) / int(m.group(2))
    raise reader.error(f"Invalid number '{token}'")


_MACROS = {
    '"': _read_string,
    "\\": _read_char,
    ":": _read_keyword,
    "(": _read_list,
    "[": _read_vector,
    "{": _read_map,
    "#": _read_dispatch,
    "'": _read_quote,
}


# Writing

LINE_WIDTH = 100

# Lists written with their body forms on lines of their own, e.g.
# (defn name [params]
#   body)
BODY_FORMS = {"fn": 1, "defn": 2, "if": 1}  # head -> forms kept on the first line

WRITE_ESCAPES = {v: "\\" + k for k, v in STRING_ESCAPES.items()}


def writes(value, indent=0):
    """`value` as edn text.

    A collection holding other collections is laid out over several
    lines when it doesn't fit on one; `indent` is the column it starts
    at, for laying out nested collections.
    """
    if isinstance(value, dict):
        return _write_map(value, indent)
    if isinstance(value, List) and value and value[0] in BODY_FORMS:
        return _write_body_form(value, indent)
    if isinstance(value, (list, set)):
        start, end, step = _brackets(value)
        inline = _inline(value)
        if not any(_is_collection(item) for item in value) or (
                len(inline) <= LINE_WIDTH - indent):
            return inline
        separator = "\n" + " " * (indent + step)
        items = [writes(item, indent + step) for item in value]
        return start + separator.join(items) + end
    return _write_atom(value)


def _write_map(value, indent):
    if not any(_is_collection(v) for v in value.values()):
        return _inline(value)
    pad = " " * (indent + 2)
    lines = [f"{pad}{writes(k, indent + 2)} {writes(v, indent + 2)}"
             for k, v in value.items()]
    return "{\n" + "\n".join(lines) + "\n" + " " * indent + "}"


def _write_body_form(value, indent):
    kept = BODY_FORMS[str(value[0])] + 1
    first_line = "(" + " ".join(_inline(item) for item in value[:kept])
    body = [" " * (indent + 2) + writes(item, indent + 2) for item in value[kept:]]
    return "\n".join([first_line, *body]) + ")"


def _inline(value):
    """`value` as edn on one line"""
    if isinstance(value, dict):
        pairs = [f"{_inline(k)} {_inline(v)}" for k, v in value.items()]
        return "{" + " ".join(pairs) + "}"
    if isinstance(value, (list, set)):
        start, end, _ = _brackets(value)
        return start + " ".join(_inline(item) for item in value) + end
    return _write_atom(value)


def _brackets(value):
    """(start, end, indent of items on lines of their own)"""
    if isinstance(value, set):
        return "#{", "}", 1
    if isinstance(value, List):
        return "(", ")", 4
    return "[", "]", 1


def _is_collection(value):
    return isinstance(value, (list, dict, set))


def _write_atom(value):
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Symbol):
        return str(value)
    if isinstance(value, str):
        return '"' + "".join(_write_char(ch) for ch in value) + '"'
    return repr(value)


def _write_char(ch):
    if ch in WRITE_ESCAPES:
        return WRITE_ESCAPES[ch]
    if ord(ch) < 0x20 or ord(ch) == 0x7F:
        return f"\\u{ord(ch):04x}"
    return ch
