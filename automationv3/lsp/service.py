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

from ..framework import closure as closures, edn, lisp, refs, snippets, source
from ..framework.analysis import ERROR, KNOWN_FORMS, WARNING
from ..framework.block import block_names, documented
from ..framework.language import DEFINITIONS, DIRECTIVES, PRECONDITION, head, name_of

BLOCK, FUNCTION, VARIABLE, KEYWORD = "block", "function", "variable", "keyword"
REQUIREMENT = "requirement"
PATH = "path"
REQ_OPEN = re.compile(r":req:`([^`]*)\Z", re.IGNORECASE)
LITERALS = (str, int, float, bool, type(None))
DELIMITERS = "()[]{}\"';,"
CONSTRUCTOR_STRING = re.compile(r"\(\s*([^\s()\[\]{}\"';,]+)\s+\"([^\"\\\\]*)\Z")
PREFIX = re.compile(r"[^\s()\[\]{}\"';,]*\Z")
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
    start: int = None  # the column the text it replaces starts at, when not the name's


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
            if first == "fn" and len(frame.items) > 1 and isinstance(frame.items[1], str) \
                    and frame.items[1] != '"':
                found.append(frame.items[1])  # (fn f [x] (f ...)): its own name
        if vector is not None:
            for target in vector.items[::every]:
                found += frame_names(target)
    return found


def frame_names(target):
    """The names a binding pattern binds, as `scan` read it (possibly
    cut off at the end): a name, [a b & more :as all] or
    {a :a :keys [b] :or {b 1} :as m}"""
    if isinstance(target, str):
        return [] if target in ("&", '"') or target.startswith(":") else [target]
    if target.char == "[":
        return [name for item in target.items for name in frame_names(item)]
    if target.char != "{":
        return []
    found, items = [], target.items
    for key, value in zip(items[::2], items[1::2]):
        if key in (":keys", ":strs", ":syms") and isinstance(value, Frame):
            found += [n.lstrip(":") for n in value.items if isinstance(n, str) and n != '"']
        elif key == ":as" and isinstance(value, str):
            found += frame_names(value)
        elif not (isinstance(key, str) and key.startswith(":")):
            found += frame_names(key)
    return found


def binder_names(form):
    """The names a let, fn or defn form binds for its body"""
    from ..framework.language import parse_fn_arities, pattern_names, pattern_problem
    if head(form) == "let":
        targets = list(form[1])[::2] if len(form) > 1 and isinstance(form[1], edn.Vector) else []
    else:
        name, signatures = parse_fn_arities(form)
        targets = [s[0] for s in signatures
                   if isinstance(s, list) and s and isinstance(s[0], edn.Vector)]
        if head(form) == "fn" and name is not None:  # its body may call it by name
            targets.append(name)
    return {str(n) for t in targets if not pattern_problem(t) for n in pattern_names(t)}


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


def ref_maker(name):
    """The kind of ref the function `name` makes: it is the kind of ref
    itself, or is marked with refs.constructs; else None"""
    function = {str(k): v for k, v in lisp.global_env.items()}.get(name)
    if isinstance(function, type) and issubclass(function, refs.Ref):
        return function
    return getattr(function, "ref_type", None)


@dataclass
class Missing:
    """A path that doesn't exist: the first name of it that isn't below
    what comes before it"""
    parent: str
    name: str
    there: list  # the Childs that are below `parent`

    def message(self, kind):
        names = ", ".join(c.name for c in self.there[:12]) + (", ..." if len(self.there) > 12 else "")
        where = f"{kind} {self.parent}" if self.parent else kind
        return (f"no {self.name} below {where}" + (f" (there: {names})" if names else "")
                + "; a run will fail when it reaches it")


def lookup(ref_type, path, cache=None):
    """The refs.Child at `path`, Missing, or None when its kind of ref
    can't say"""
    cache = {} if cache is None else cache
    parts = path.split(".")
    child = None
    for n, part in enumerate(parts):
        parent = ".".join(parts[:n])
        key = (ref_type, parent)
        if key not in cache:
            cache[key] = ref_type.children(parent)
        found = cache[key]
        if found is None:
            return None
        child = next((c for c in found if c.name == part), None)
        if child is None:
            return Missing(parent, part, found)
    return child


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
        found = self.check_code(path, text)
        return (found + [(path, p) for p in self.prose_problems(path, text)]
                + [(path, p) for p in self.missing_paths(path, text)]
                + [(path, p) for p in self.unknown_requirements(text)])

    def prose_problems(self, path, text):
        """What docutils finds wrong in a script's rst, at error level (a
        heading that skips a level, or one inside a variant at its
        section's level): what the page would show as an error"""
        if not source.has_rvt(text):
            return []
        tree = source.parse(text, path)
        blocks = source.unreadable(tree)
        return [Problem(ERROR, p.message, p.span.line - 1, p.span.col, p.span.end_line - 1,
                        max(p.span.end_col, p.span.col + 1))
                for p in source.problems(tree) if p not in blocks]

    def missing_paths(self, path, text):
        """Warnings for the ref paths a script names that its kind of ref
        says don't exist: a dotted name below a ref or group, or the path
        a ref is made with"""
        definitions, cache, found = self.definitions(path), {}, []
        closure = self.resolved.get(path)
        shadowed = set(closure.uuts) if closure else set()
        if closure is not None:
            shadowed |= {str(s) for v in closure.variations for s in v.symbols}

        def report(span, message):
            end = span.end_col if span.end_line == span.line else span.col + 1
            found.append(Problem(WARNING, message, span.line - 1, span.col, span.line - 1, end))

        def walk(form, bound):
            if isinstance(form, edn.Symbol) and not isinstance(form, edn.Keyword):
                name = str(form)
                base, dot, rest = name.partition(".")
                span = edn.span_of(form)
                if not dot or not base or base in bound or base in shadowed or span is None:
                    return
                value = self.static(name, definitions)
                if value is None or value.kind == "literal":
                    return
                members = [("", value)] if value.kind == "ref" else value.members
                base_value = self.static(base, definitions)
                bases = [base_value] if base_value.kind == "ref" else [m for _, m in base_value.members]
                for (label, member), start in zip(members, bases):
                    missing = lookup(member.ref_type, member.path, cache)
                    # only what this name adds: the base's own path is checked where it is made
                    if isinstance(missing, Missing) and len(f"{missing.parent}.{missing.name}".strip(".")) \
                            > len(start.path):
                        report(span, (f"{label}: " if label else "")
                               + missing.message(member.ref_type.__name__))
                        return
                return
            if isinstance(form, dict):
                for key, value in form.items():
                    walk(key, bound)
                    walk(value, bound)
                return
            if not isinstance(form, (list, edn.Vector, set, frozenset)):
                return
            items = list(form)
            if isinstance(form, list) and items:
                first = head(form)
                ref_type = ref_maker(first) if first else None
                if ref_type is not None and len(items) == 2 and isinstance(items[1], str):
                    missing = lookup(ref_type, items[1], cache)
                    span = edn.span_of(form)
                    if isinstance(missing, Missing) and span is not None:
                        report(span, missing.message(ref_type.__name__))
                if first in BINDERS:
                    bound = bound | binder_names(form)
            for item in items:
                walk(item, bound)

        for block in self.blocks(path, text):
            for form, _ in block.forms:
                walk(form, frozenset())
        return found

    def requirement_refs(self, text):
        """[(id, line, col, end col)] of the :req: references in prose,
        0-based, the columns those of what is between the backquotes"""
        return [(id, line, start, end) for id, line, _, start, end in self.requirement_roles(text)]

    def requirement_roles(self, text):
        """[(id, line, role's col, id's col, id's end col)], 0-based, of
        the :req: references in prose (the role ends one past the id)"""
        found = []
        for id, span in source.requirement_refs(source.parse(text)):
            if span is not None:
                raw = text.splitlines()[span.line - 1][span.col:span.end_col]
                found.append((id, span.line - 1, span.col, span.col + raw.index("`") + 1,
                              span.end_col - 1))
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
        if PurePosixPath(path).name == closures.CORE:
            _, diagnostics = closures.check_core(path, text)
            return [(path, self.placed(d, path)) for d in diagnostics]
        if snippets.is_snippets(path):
            return [(path, self.problem_at(problem)) for problem in snippets.read(text, path)[1]]
        if not closures.is_script(path, text):
            return []
        try:
            closure = closures.resolve(self.root, path, text, self.texts)
        except Exception as e:  # a file it loads is gone or unreadable
            return [(path, self.whole(text, str(e)))]
        self.resolved[path] = closure
        found = []
        for d in closure.diagnostics:
            where = (d.span.source if d.span is not None else None) or d.path or path
            found.append((where, self.placed(d, where)))
        return found

    def placed(self, d, where):
        """A Diagnostic as a Problem: on its span, or on the whole of the
        file `where` if it has none"""
        scope = ""
        if d.variations:
            scope = f" (in variation{'s' if len(d.variations) > 1 else ''} {', '.join(d.variations)})"
        if d.span is None:
            return self.whole(self.text(where) or "", d.message + scope, d.severity)
        s = d.span
        end_col = s.end_col if (s.end_line, s.end_col) > (s.line, s.col) else s.col + 1
        return Problem(d.severity, d.message + scope, s.line - 1, s.col, s.end_line - 1, end_col)

    def whole(self, text, message, severity=ERROR):
        """A problem with the document as a whole: shown on its first line"""
        first = text.splitlines()[0] if text else ""
        return Problem(severity, message, 0, 0, 0, max(len(first), 1))

    def problem_at(self, problem):
        """A source.Problem as a Problem, an error"""
        s = problem.span
        return Problem(ERROR, problem.message, s.line - 1, s.col, s.end_line - 1,
                       max(s.end_col, s.col + 1) if s.end_line == s.line else s.end_col)

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
        typed = CONSTRUCTOR_STRING.search(code)
        if typed is not None:  # the path of a ref being made: (connector "lm.e
            return self.constructor_paths(typed.group(1), typed.group(2), col)
        word = PREFIX.search(code)
        stack = scan(code[:word.start()])
        if stack is None:
            return []
        if "." in word.group() and not word.group().startswith("."):
            found = self.ref_paths(path, word.group(), col, local_names(stack))
            if found is not None:
                return found
        at_head = bool(stack) and stack[-1].char == "(" and not stack[-1].items
        found = self.names(path, text)
        for name in local_names(stack):
            found[name] = Item(name, VARIABLE, "bound here")
        return [item for item in found.values() if at_head or not item.head]

    def ref_paths(self, path, word, col, bound):
        """The Items completing `word`, a dotted name being typed whose
        base is a ref or group, or None when it isn't one"""
        prefix, _, _ = word.rpartition(".")
        if prefix.partition(".")[0] in bound:
            return None
        value = self.static(prefix, self.definitions(path))
        if value is None or value.kind == "literal":
            return None
        found = self.children_of(value)
        if found is None:
            return None
        start = col - len(word)
        return [Item(f"{prefix}.{c.name}", PATH, c.detail, c.doc, start=start) for c in found]

    def constructor_paths(self, function, typed, col):
        """The Items completing the path in (constructor "typed"""
        ref_type = ref_maker(function)
        if ref_type is None:
            return []
        parent, _, _ = typed.rpartition(".")
        found = ref_type.children(parent) or []
        start = col - len(typed)
        return [Item(f"{parent}.{c.name}" if parent else c.name, PATH, c.detail, c.doc,
                     start=start) for c in found]

    def children_of(self, value):
        """The refs.Childs below a ref, or those every member of a group
        has; None when its kind of ref can't say"""
        if value.kind == "ref":
            return value.ref_type.children(value.path)
        shared = None
        for _, member in value.members:
            found = member.ref_type.children(member.path)
            if found is None:
                return None
            if shared is None:
                shared = list(found)
            else:
                names = {c.name for c in found}
                shared = [c for c in shared if c.name in names]
        return shared or []

    def code_before(self, text, lines, line, col):
        """The code of the block `line` is in, up to `col` of it, or None
        if the place isn't in a block's code"""
        for block in source.walk(source.parse(text)):
            first, last = block.line_start - 1, block.line_end - 1
            while last + 1 < len(lines) and not lines[last + 1].strip():
                last += 1  # the blank lines after it
            if not first <= line <= last:
                continue
            if block.problems:
                pass  # edited as the rst it is: all of it is code
            elif isinstance(block, source.rvt_variant):
                continue  # what is inside it says
            elif block.content_line and line >= block.content_line - 1:
                first = block.content_line - 1
            else:
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
        for name in sorted(special | DIRECTIVES | {PRECONDITION}):
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
        for name, definition in self.definitions(path).items():
            where = "here" if definition.path == path else definition.path
            form = definition.form
            if head(form) == "defn":
                params = edn.writes(form[2]) if len(form) > 2 and isinstance(form[2], edn.Vector) \
                    else "defn"
                add(Item(name, FUNCTION, f"{params} in {where}"))
            else:
                add(Item(name, VARIABLE, f"def in {where}"))
        if closure is None:  # not read cleanly yet: the handles as declared, last wins
            declared = [form for where in chain + [path]
                        for block in self.blocks(where, text if where == path
                                                 else self.text(where) or "")
                        for form, _ in block.forms if head(form) == "uut"]
            for name in ([name_of(v) for v in declared[-1][1:]] if declared else []):
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
        for where in self.sources(path):
            for block in self.blocks(where, self.text(where) or ""):
                code, first = block.code.splitlines(), block.content_line
                for form, span in block.forms:  # of one being typed, what reads
                    if (head(form) in DEFINITIONS and len(form) >= 2
                            and isinstance(form[1], edn.Symbol) and span is not None):
                        written = "\n".join(code[span.line - first:span.end_line - first + 1])
                        found[str(form[1])] = Definition(str(form[1]), form, where,
                                                         span.line - 1, written)
        return found

    def blocks(self, path, text):
        """The rvt blocks of `text` that read as blocks (a block with a
        wrong option is rst to edit, not code), at any depth"""
        return [block for block in source.walk(source.parse(text, path))
                if isinstance(block, source.rvt_block) and not block.problems]

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
        ref_type = ref_maker(str(form[0]))
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
        for id, at, role, start, end in self.requirement_roles(text):
            if at == line and role <= col <= end + 1:
                return self.requirement_hover(id), start, end
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
                return f"`{name}` is a {value.describe()}." + self.path_detail(value)
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

    def path_detail(self, value):
        """What the plugin says of a ref's path, or that it doesn't exist"""
        members = [("", value)] if value.kind == "ref" else value.members
        said = []
        for name, member in members:
            found = lookup(member.ref_type, member.path)
            if isinstance(found, Missing):
                said.append(f"{name + ': ' if name else ''}{found.message(member.ref_type.__name__)}.")
            elif found is not None:
                words = ", ".join(w for w in (found.detail, found.doc) if w)
                if words:
                    said.append(f"{name + ': ' if name else ''}{words}.")
        return "\n\n" + "\n".join(f"- {s}" if len(members) > 1 else s for s in said) if said else ""

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
        from ..framework.language import fn_params, is_name
        found = []
        for params in fn_params(function):
            labels, variadic = [], False
            for param in params:
                if is_name(param) or isinstance(param, (edn.Vector, dict)):
                    shown = str(param) if is_name(param) else edn.writes(param)
                    labels.append(shown + ("..." if variadic else ""))
                elif str(param) == "&":
                    variadic = True
            found.append(Signature(f"({' '.join([name] + labels)})", labels, f"Defined in {definition.path}."))
        return found
