"""What the language server answers from: the problems in the documents
an editor has open, and the names that complete at a place in one

A Service is for one scripts root. `texts` holds the documents the
editor has open, by path relative to the root, as the editor has them:
they stand in for the files on disk, so a script is checked against the
core.rst being edited beside it.

Lines and columns here are 0-based, columns counting characters.
"""

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..framework import cards, closure as closures, document, edn, lisp
from ..framework.analysis import ERROR, KNOWN_FORMS, WARNING
from ..framework.block import block_names, documented
from ..framework.cards import RVT, SOURCE
from ..framework.language import DIRECTIVES, PRECONDITION

BLOCK, FUNCTION, VARIABLE, KEYWORD = "block", "function", "variable", "keyword"
DELIMITERS = "()[]{}\"';,"
PREFIX = re.compile(r"[^\s()\[\]{}\"';,]*\Z")
DEFINITION = re.compile(r"\(\s*(def|defn)\s+([^\s()\[\]{}\"';,]+)(?:\s+(\[[^\]]*\]))?")
UUTS = re.compile(r"\(\s*uut\s+([^()]*)\)")
BINDERS = {"fn", "defn", "let"}


@dataclass
class Problem:
    severity: str  # analysis.ERROR or WARNING
    message: str
    line: int = 0
    col: int = 0
    end_line: int = 0
    end_col: int = 0


@dataclass
class Item:
    """A name that completes"""
    label: str
    kind: str
    detail: str = ""
    doc: str = ""
    head: bool = False  # only makes sense first in a call


class Frame:
    """A bracket that is open: its opener and what it holds so far
    (names, and the brackets closed inside it)"""

    def __init__(self, char):
        self.char, self.items = char, []


def scan(code):
    """The brackets still open at the end of `code`, outermost first, or
    None if `code` ends inside a string or a comment"""
    stack, i, n = [], 0, len(code)

    def add(item):
        if stack:
            stack[-1].items.append(item)

    while i < n:
        ch = code[i]
        if ch == ";":
            end = code.find("\n", i)
            if end < 0:
                return None
            i = end
        elif ch == '"':
            i += 1
            while i < n and code[i] != '"':
                i += 2 if code[i] == "\\" else 1
            if i >= n:
                return None
            add('"')
        elif ch == "\\":
            i += 1
        elif ch in "([{":
            frame = Frame(ch)
            add(frame)
            stack.append(frame)
        elif ch in ")]}":
            if stack:
                stack.pop()
        elif not ch.isspace() and ch != ",":
            start = i
            while i < n and not code[i].isspace() and code[i] not in DELIMITERS:
                i += 1
            add(code[start:i])
            continue
        i += 1
    return stack


def local_names(stack):
    """The names bound around the end of the code `scan` read: the
    parameters of the fn and defn forms it is in, and what let binds"""
    found = []
    for frame in stack:
        if frame.char != "(" or not frame.items:
            continue
        first, vector = frame.items[0], None
        if isinstance(first, Frame) and first.char == "[":
            vector, every = first, 1  # one arity of a fn or defn: ([a b] ...)
        elif first in BINDERS:
            vector = next((i for i in frame.items[1:]
                           if isinstance(i, Frame) and i.char == "["), None)
            every = 2 if first == "let" else 1
        if vector is not None:
            found += [name for name in vector.items[::every]
                      if isinstance(name, str) and name not in ("&", '"')]
    return found


class Service:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.texts = {}  # the open documents: path -> text
        self.resolved = {}  # path -> the closure of its last check

    def text(self, path):
        """The text of `path`: as open, else as on disk, else None"""
        if path in self.texts:
            return self.texts[path]
        try:
            return (self.root / path).read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    # Problems

    def problems(self):
        """{path: [Problem]} for the open documents and the files they
        load; a path with nothing wrong has an empty list"""
        found = {path: [] for path in self.texts}
        for path in sorted(self.texts):
            for where, problem in self.check(path):
                if problem not in found.setdefault(where, []):
                    found[where].append(problem)
        return found

    def check(self, path):
        """[(path, Problem)] from checking the open document `path`"""
        text = self.texts[path]
        if PurePosixPath(path).suffix != ".rst":
            return []
        unread = self.unreadable(text)
        if unread:
            return [(path, problem) for problem in unread]
        if PurePosixPath(path).name == closures.CORE:
            return [(path, self.whole(text, message)) for message in self.core_errors(path, text)]
        if not closures.is_script(path, text):
            return []
        try:
            closure = closures.resolve(self.root, path, text, self.texts)
        except Exception as e:  # a file it loads is gone or unreadable
            return [(path, self.whole(text, str(e)))]
        self.resolved[path] = closure
        found = []
        for d in closure.diagnostics:
            scope = ""
            if d.variations:
                scope = f" (in variation{'s' if len(d.variations) > 1 else ''} {', '.join(d.variations)})"
            where = (d.span.source if d.span is not None else None) or d.path or path
            if d.span is None:
                problem = self.whole(self.text(where) or "", d.message + scope, d.severity)
            else:
                s = d.span
                end_col = s.end_col if (s.end_line, s.end_col) > (s.line, s.col) else s.col + 1
                problem = Problem(d.severity, d.message + scope, s.line - 1, s.col,
                                  s.end_line - 1, end_col)
            found.append((where, problem))
        analysed = {str(d) for d in closure.diagnostics}
        for message in closure.errors:
            if message in analysed:
                continue
            where = next((p for p in closure.load_order if message.startswith(f"{p}: ")), None)
            if where is not None:
                message = message[len(where) + 2:]
            where = where or path
            found.append((where, self.whole(self.text(where) or "", message)))
        return found

    def whole(self, text, message, severity=ERROR):
        """A problem with the document as a whole: shown on its first line"""
        first = text.splitlines()[0] if text else ""
        return Problem(severity, message, 0, 0, 0, max(len(first), 1))

    def unreadable(self, text):
        """Problems for the blocks of `text` that can't be read at all,
        each where the reader stopped"""
        found = []
        for card in cards.split(text):
            if card.kind == RVT:
                try:
                    edn.read_all_with_spans(card.code)
                except edn.ParseError as e:
                    line, col = card.code_line - 1 + e.line, card.code_indent + e.col
                    message = str(e).rsplit(" (line:", 1)[0]
                    found.append(Problem(ERROR, message, line, col, line, col + 1))
            elif card.kind == SOURCE:
                try:
                    document.parse(card.source)
                except Exception as e:
                    lead = len(card.source) - len(card.source.lstrip("\r\n"))
                    line = card.line - 1 + card.source[:lead].count("\n")
                    message = re.sub(r"\A<string>:\d+: \(\w+/\d\) ", "", str(e))
                    message = message.rsplit(" (line:", 1)[0].split(" .. rvt", 1)[0]
                    width = len(card.source.lstrip("\r\n").splitlines()[0])
                    found.append(Problem(ERROR, message, line, 0, line, max(width, 1)))
        return found

    def core_errors(self, path, text):
        """What closure.resolve would say of a core.rst, as messages"""
        errors = []
        parts = closures.read_parts(path, text, errors)
        errors += closures.lint(path, [part.form for part in parts if not part.prose])
        if any(part.table is not None for part in parts):
            errors.append(f"{path}: core.rst blocks can't be tables")
        errors += closures.lint_variation_scopes(path, parts, [])
        return [e[len(path) + 2:] if e.startswith(f"{path}: ") else e for e in errors]

    # Completion

    def complete(self, path, line, col):
        """The Items that complete at `line`, `col` of `path`: none
        outside a block's code, or inside a string or a comment"""
        text = self.text(path)
        if text is None or PurePosixPath(path).suffix != ".rst":
            return []
        lines = text.splitlines()
        if line >= len(lines):
            return []
        code = self.code_before(text, lines, line, col)
        if code is None:
            return []
        stack = scan(code[:PREFIX.search(code).start()])
        if stack is None:
            return []
        at_head = bool(stack) and stack[-1].char == "(" and not stack[-1].items
        found = self.names(path, text)
        for name in local_names(stack):
            found[name] = Item(name, VARIABLE, "bound here")
        return [item for item in found.values() if at_head or not item.head]

    def code_before(self, text, lines, line, col):
        """The code of the block `line` is in, up to `col` of it, or None
        if the place isn't in a block's code"""
        for card in cards.split(text):
            first = card.line - 1
            last = first + len(card.source.splitlines())
            if not first <= line < last:
                continue
            if card.kind == RVT and line >= card.code_line - 1:
                first = card.code_line - 1
            elif card.kind != SOURCE:
                return None
            return "\n".join(lines[first:line] + [lines[line][:col]])
        return None

    def names(self, path, text):
        """{name: Item} for every name a block of `path` can use"""
        found = {}

        def add(item):
            found[item.label] = item

        for name, value in lisp.global_env.items():
            add(Item(str(name), FUNCTION if callable(value) else VARIABLE, "builtin"))
        special = {n for n in lisp.special_forms if isinstance(n, str)} | KNOWN_FORMS
        for name in sorted(special | DIRECTIVES | {PRECONDITION, "TBD"}):
            add(Item(name, KEYWORD, head=True))
        from ..framework.plugins import load_plugins
        load_plugins()
        for name in sorted(block_names()):
            block = documented(name)
            add(Item(name, BLOCK, block.usage().splitlines()[0], block.doc(), head=True))
        closure = self.resolved.get(path)
        chain = [p for p in closures.ancestors(path)
                 if p != path and self.text(p) is not None]
        imports = [p for p in (closure.imports if closure else []) if p not in chain]
        for source in chain + imports + [path]:
            for kind, name, params in DEFINITION.findall(
                    text if source == path else self.text(source) or ""):
                where = "here" if source == path else source
                if kind == "defn":
                    add(Item(name, FUNCTION, f"{params or 'defn'} in {where}".strip()))
                else:
                    add(Item(name, VARIABLE, f"def in {where}"))
        if closure is None:  # not read cleanly yet: the handles as declared, last wins
            declared = [found for source in chain + [path] for found in UUTS.findall(
                text if source == path else self.text(source) or "")]
            for name in (declared[-1].replace(":", " ").split() if declared else []):
                add(Item(name, VARIABLE, "UUT handle"))
        else:
            for name in closure.uuts:
                add(Item(name, VARIABLE, "UUT handle"))
            for symbol in dict.fromkeys(s for v in closure.variations for s in v.symbols):
                add(Item(str(symbol), VARIABLE, "variation value"))
        return found
