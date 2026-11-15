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

from ..framework import cards, closure as closures, document, edn, lisp, refs
from ..framework.analysis import ERROR, KNOWN_FORMS, WARNING
from ..framework.block import block_names, documented
from ..framework.cards import RVT, SOURCE
from ..framework.language import DEFINITIONS, DIRECTIVES, PRECONDITION, head

BLOCK, FUNCTION, VARIABLE, KEYWORD = "block", "function", "variable", "keyword"
REQUIREMENT = "requirement"
REQ = re.compile(r":req:`([^`]+)`", re.IGNORECASE)
REQ_OPEN = re.compile(r":req:`([^`]*)\Z", re.IGNORECASE)
LITERALS = (str, int, float, bool, type(None))
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


@dataclass
class Definition:
    """A top-level def or defn, as written"""
    name: str
    form: list
    path: str
    line: int  # where it starts in its file
    source: str  # its code


@dataclass
class Static:
    """What a name is, as far as it can be told without running
    anything: a literal, a ref, or a group of refs"""
    kind: str  # "literal", "ref" or "group"
    text: str = ""  # a literal, as written
    ref_type: type = None
    path: str = ""
    members: list = None  # a group's: [(name, Static ref)]

    def child(self, rest):
        """What `name.rest` is, for a ref or a group"""
        if self.kind == "ref":
            return Static("ref", ref_type=self.ref_type, path=f"{self.path}.{rest}")
        if self.kind == "group":
            return Static("group", members=[(name, ref.child(rest)) for name, ref in self.members])
        return None

    def describe(self):
        if self.kind == "literal":
            return f"`{self.text}`"
        if self.kind == "ref":
            return f"{self.ref_type.__name__} ref `{self.path}`"
        return "group of " + ", ".join(f"{name}: {ref.describe()}" for name, ref in self.members)


@dataclass
class Signature:
    label: str
    parameters: list  # their labels, as they appear in `label`
    doc: str = ""


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


def is_literal(form):
    """A value that is what it says: a number, string, keyword, or a
    collection of those"""
    if isinstance(form, edn.Keyword):
        return True
    if isinstance(form, edn.Symbol):
        return str(form) in ("true", "false", "nil")
    if isinstance(form, (edn.Vector, dict, set, frozenset)):
        items = list(form.items()) if isinstance(form, dict) else list(form)
        return all(is_literal(i) for item in items
                   for i in (item if isinstance(item, tuple) else (item,)))
    return isinstance(form, LITERALS)


def name_at(text, col):
    """(name, start, end) of the name around `col` of a line, or None"""
    start = end = col
    while start > 0 and not text[start - 1].isspace() and text[start - 1] not in DELIMITERS:
        start -= 1
    while end < len(text) and not text[end].isspace() and text[end] not in DELIMITERS:
        end += 1
    return (text[start:end], start, end) if end > start else None


class Service:
    def __init__(self, root, requirements=None):
        """`requirements` answers `find(id)` (a Requirement or None) and
        `all()` (every Requirement of the context the root verifies; may
        be empty when they can't be listed)"""
        from ..framework.plugins import load_plugins
        load_plugins()  # their blocks, functions and ref kinds
        self.root = Path(root).resolve()
        self.requirements = requirements
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
        return self.check_code(path, text) + [(path, p) for p in self.unknown_requirements(text)]

    def requirement_refs(self, text):
        """[(id, line, col, end col)] of the :req: references in prose"""
        found = []
        for card in cards.split(text):
            if card.kind != cards.PROSE:
                continue
            for n, line in enumerate(card.source.splitlines()):
                found += [(m.group(1).strip(), card.line - 1 + n, m.start(1), m.end(1))
                          for m in REQ.finditer(line)]
        return found

    def unknown_requirements(self, text):
        """Warnings for the :req: ids that aren't requirements, when the
        requirements can be listed"""
        known = {r.id for r in self.requirements.all()} if self.requirements else set()
        if not known:
            return []
        return [Problem(WARNING, f"{id} isn't a requirement in the requirements this "
                        "workspace verifies", line, col, line, end)
                for id, line, col, end in self.requirement_refs(text) if id not in known]

    def check_code(self, path, text):
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
        if REQ_OPEN.search(lines[line][:col]):
            return [Item(r.id, REQUIREMENT, " ".join((r.text or "").split())[:90], r.text or "")
                    for r in (self.requirements.all() if self.requirements else [])]
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

    # What names are

    def sources(self, path):
        """The files whose definitions `path` sees, in load order"""
        closure = self.resolved.get(path)
        chain = [p for p in closures.ancestors(path) if p != path and self.text(p) is not None]
        imports = [p for p in (closure.imports if closure else []) if p not in chain]
        return chain + imports + [path]

    def definitions(self, path):
        """{name: Definition} for the top-level definitions `path` sees:
        a later file's replaces an earlier one's. A block that can't
        all be read gives what comes before the trouble."""
        found = {}
        for source in self.sources(path):
            for card in cards.split(self.text(source) or ""):
                if card.kind != RVT:
                    continue
                # what reads, of a block still being typed
                forms = edn.read_all_with_spans(card.code, readable=True)
                code = card.code.splitlines()
                for form, span in forms:
                    if (head(form) in DEFINITIONS and len(form) >= 2
                            and isinstance(form[1], edn.Symbol) and span is not None):
                        written = "\n".join(code[span.line:span.end_line + 1])
                        found[str(form[1])] = Definition(
                            str(form[1]), form, source, card.code_line - 1 + span.line, written)
        return found

    def static(self, name, definitions, seen=()):
        """What `name` is, if a literal, an alias of one, a ref or a
        group says so; None when only a run can tell"""
        if name in seen:
            return None
        if name in definitions:
            form = definitions[name].form
            if head(form) != "def" or len(form) != 3:
                return None
            return self.static_value(form[2], definitions, seen + (name,))
        base, _, rest = name.partition(".")
        if rest and base in definitions:
            found = self.static(base, definitions, seen)
            return found.child(rest) if found is not None else None
        return None

    def static_value(self, form, definitions, seen):
        if is_literal(form):
            return Static("literal", edn.writes(form))
        if isinstance(form, edn.Symbol):
            return self.static(str(form), definitions, seen)
        if not isinstance(form, list) or not form or not isinstance(form[0], edn.Symbol):
            return None
        function = {str(k): v for k, v in lisp.global_env.items()}.get(str(form[0]))
        # A function that makes refs: the kind of ref itself, or one marked
        # with refs.constructs
        ref_type = function if isinstance(function, type) and issubclass(function, refs.Ref) \
            else getattr(function, "ref_type", None)
        if ref_type is not None and len(form) == 2 and isinstance(form[1], str):
            return Static("ref", ref_type=ref_type, path=form[1])
        if str(form[0]) == "group" and len(form) > 1:
            members = []
            for item in form[1:]:
                found = self.static_value(item, definitions, seen)
                if found is None or found.kind == "literal":
                    return None
                if found.kind == "group":
                    members += found.members
                else:
                    members.append((str(item), found))
            return Static("group", members=members)
        return None

    # Hover

    def hover(self, path, line, col):
        """(markdown, start col, end col) for what is at a place, or None"""
        text = self.text(path)
        if text is None or PurePosixPath(path).suffix != ".rst":
            return None
        lines = text.splitlines()
        if line >= len(lines):
            return None
        for m in REQ.finditer(lines[line]):
            if m.start() <= col <= m.end():
                return self.requirement_hover(m.group(1).strip()), m.start(1), m.end(1)
        at = name_at(lines[line], col)
        if at is None:
            return None
        name, start, end = at
        code = self.code_before(text, lines, line, end)  # the name included: it may bind itself
        stack = scan(code) if code is not None else None
        if stack is None or name.startswith(":"):
            return None
        found = self.describe(path, name, stack)
        return (found, start, end) if found else None

    def requirement_hover(self, id):
        found = self.requirements.find(id) if self.requirements else None
        if found is None or not found.text:
            return f"**{id}** isn't a requirement in the requirements this workspace verifies." \
                if self.requirements else None
        where = f" ({found.spec})" if found.spec else ""
        return f"**{id}**{where}\n\n{found.text.strip()}"

    def describe(self, path, name, stack):
        """Markdown saying what `name` is in a block of `path`"""
        if name in local_names(stack):
            return f"`{name}`: a parameter or a `let` name"
        definitions = self.definitions(path)
        if name in definitions:
            d = definitions[name]
            where = "this script" if d.path == path else d.path
            parts = [f"```clojure\n{d.source}\n```", f"Defined in {where}."]
            value = self.static(name, definitions)
            if value is not None and value.kind != "literal":
                parts.insert(1, f"`{name}` is a {value.describe()}.")
            elif value is not None and not is_literal(d.form[2]):
                parts.insert(1, f"`{name}` is {value.describe()}.")
            return "\n\n".join(parts)
        if "." in name:
            value = self.static(name, definitions)
            if value is not None:
                return f"`{name}` is a {value.describe()}."
            name = name.partition(".")[0]  # say what it is a path of
            if name in definitions:
                return self.describe(path, name, stack)
        closure = self.resolved.get(path)
        if closure is not None and name in closure.uuts:
            return f"`{name}`: the handle of the UUT `{name}`, bound when the script runs."
        if closure is not None and closure.variations and name in closure.variations[0].symbols:
            at = closure.variations[0].symbols.index(name)
            rows = "\n".join(f"- {v.name}: `{edn.writes(v.forms[at])}`" for v in closure.variations)
            return f"`{name}`: a variation value.\n\n{rows}"
        from ..framework.plugins import load_plugins
        load_plugins()
        if name in block_names():
            block = documented(name)
            return f"```clojure\n{block.usage()}\n```\n\n{block.doc()}".strip()
        builtins = {str(k): v for k, v in lisp.global_env.items()}
        if name in builtins:
            doc = (getattr(builtins[name], "__doc__", None) or "").strip().split("\n\n")[0]
            kind = "function" if callable(builtins[name]) else "value"
            return f"`{name}`: a builtin {kind}." + (f"\n\n{' '.join(doc.split())}" if doc else "")
        return None

    # Signatures

    def signatures(self, path, line, col):
        """([Signature], which one, which parameter) for the call the
        place is in, or None"""
        text = self.text(path)
        if text is None or PurePosixPath(path).suffix != ".rst":
            return None
        lines = text.splitlines()
        if line >= len(lines):
            return None
        code = self.code_before(text, lines, line, col)
        if code is None:
            return None
        stack = scan(code[:PREFIX.search(code).start()])
        definitions = None
        for frame in reversed(stack or []):
            if frame.char != "(" or not frame.items or not isinstance(frame.items[0], str):
                continue
            name, given = frame.items[0], len(frame.items) - 1
            found = self.signatures_of(path, name)
            if not found:
                continue
            fits = [n for n, s in enumerate(found)
                    if given < len(s.parameters) or (s.parameters and s.parameters[-1].endswith("..."))]
            which = fits[0] if fits else 0
            return found, which, max(min(given, len(found[which].parameters) - 1), 0)
        return None

    def signatures_of(self, path, name):
        from ..framework.plugins import load_plugins
        load_plugins()
        if name in block_names():
            block = documented(name)
            doc = block.doc().split("\n\n")[0]
            return [Signature(usage.strip(), usage.strip().strip("()").split()[1:], doc)
                    for usage in block.usage().splitlines() if usage.strip()]
        definition = self.definitions(path).get(name)
        if definition is None:
            return []
        form = definition.form
        function = form if head(form) == "defn" else form[2] if len(form) == 3 else None
        if head(function) not in ("defn", "fn"):
            return []
        rest = [i for i in function[2 if head(function) == "defn" else 1:]]
        arities = [rest[0]] if rest and isinstance(rest[0], edn.Vector) else \
            [a[0] for a in rest if isinstance(a, list) and a and isinstance(a[0], edn.Vector)]
        found = []
        for params in arities:
            labels, variadic = [], False
            for param in params:
                if str(param) == "&":
                    variadic = True
                else:
                    labels.append(str(param) + ("..." if variadic else ""))
            found.append(Signature(f"({' '.join([name] + labels)})", labels, f"Defined in {definition.path}."))
        return found
