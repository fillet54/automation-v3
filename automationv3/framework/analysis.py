"""Static analysis of a script's closure, without running anything

Definitions only appear at the top level of core.rst files and scripts,
never inside another form, so every name a script can use is known
before it runs:

- builtins (lisp.global_env) and the special forms;
- the definitions of the core.rst files in the closure;
- the script's definitions section, then its other top-level
  definitions, in order;
- the UUT handles (one per `(uut :name)`) and the variation symbols,
  bound after the definitions section loads;
- parameters of fn / defn and names bound by let, within them.

`analyze(closure)` checks every form against those, once per variation
the script declares (blocks limited to other variations don't count),
and returns Diagnostics:

- errors: an unknown name, a name used before it is defined, a
  definition anywhere but the top level, a call to a defn with a number
  of arguments none of its arities takes, a block call no form of the
  block accepts, a malformed special form, a removed form (defblock,
  passes?);
- warnings: a definition that shadows a block, a builtin or a core.rst
  definition, steps still to be written (TBD), and a step whose value is
  thrown away (a step only fails
  through a block, so `(- 10 10)` or `(= a b)` on its own checks
  nothing).

Names a core.rst function uses but the closure doesn't define are only
reported when the script can call that function: a core.rst may serve
scripts that bind more (e.g. variation symbols) than this one.
"""

import difflib
from dataclasses import dataclass, field

from . import document, edn, lisp
from .block import all_blocks, block_names
from .language import (
    DECLARATIONS, DEFINITIONS, DIRECTIVES, PRECONDITION, head, is_text, name_of,
    parse_precondition,
)

ERROR = "error"
WARNING = "warning"

# Special forms the analyzer knows the shape of. Blocks and (.method obj)
# calls are special forms too, handled on their own.
KNOWN_FORMS = {"if", "do", "def", "defn", "let", "quote", "fn", "step", "try-ok?",
               "try", "quietly"}
REMOVED = {
    "defblock": "defblock was removed: use defn. A failing block stops wherever it "
                'is called; group calls with (step "title" ...) and suppress '
                "failures explicitly with try-ok? or try",
    "passes?": "passes? was renamed try-ok?",
}
# Builtins with an effect: a step calling one isn't thrown away
EFFECTFUL = {"print"}


@dataclass
class Diagnostic:
    severity: str
    message: str
    span: edn.Span = None
    path: str = None
    variations: list = None  # the variations it applies to, None for all

    @property
    def where(self):
        if self.span is not None and self.span.source:
            return f"{self.span.source}:{self.span.line}:{self.span.col + 1}"
        return self.path or ""

    def __str__(self):
        scope = ""
        if self.variations:
            plural = "s" if len(self.variations) > 1 else ""
            scope = f" (in variation{plural} {', '.join(self.variations)})"
        return f"{self.where}: {self.message}{scope}"

    def key(self):
        return (self.severity, self.message, self.span, self.path)


@dataclass
class Definition:
    name: str
    form: list
    path: str
    index: int = None  # top-level position in the script (None in a core.rst)
    in_section: bool = False
    variations: list = None
    arities: set = None  # param counts for a defn, else None
    variadic: bool = False

    @property
    def span(self):
        return edn.span_of(self.form)


def defn_arities(form):
    """(set of parameter counts, takes any count?) of a fn or defn form"""
    rest = list(form[2:] if head(form) == "defn" else form[1:])
    if rest and isinstance(rest[0], edn.Symbol):
        rest = rest[1:]  # fn's optional name
    if rest and isinstance(rest[0], edn.Vector):
        signatures = [rest]
    else:
        signatures = rest
    counts = set()
    for signature in signatures:
        if isinstance(signature, list) and signature and isinstance(signature[0], edn.Vector):
            counts.add(len(signature[0]))
    return counts


class Names:
    """What is bound at one point of a script, for one variation"""

    def __init__(self, available, final, definitions):
        self.available = set(available)  # bound now (eager code)
        self.final = set(final)  # bound by the time any function body runs
        self.definitions = definitions  # name -> Definition (last wins)


class Analyzer:
    def __init__(self, closure, parsed=None):
        self.closure = closure
        self.script = closure.script
        self.diagnostics = []
        self.builtins = {str(k) for k in lisp.global_env}
        self.blocks = {b.name(): b for b in reversed(all_blocks())}
        self.block_names = block_names()
        self.special = {name for name in lisp.special_forms if isinstance(name, str)}
        self.parts = dict(parsed or {})
        for path in closure.load_order:
            if path in self.parts:
                continue
            try:
                self.parts[path] = document.parse(closure.files[path], path=path)
            except Exception:
                self.parts[path] = []  # closure.resolve reports it

    # Reporting

    def report(self, severity, message, form=None, parent=None, index=None, path=None):
        span = edn.span_of(form) if form is not None else None
        if span is None and parent is not None:
            span = edn.item_span(parent, index) if index is not None else None
            span = span or edn.span_of(parent)
        if isinstance(span, tuple) and not isinstance(span, edn.Span):
            span = span[0]  # a map item's (key span, value span)
        self.found.append(Diagnostic(severity, message, span,
                                     path or (span.source if span else None)))

    def error(self, message, form=None, **kw):
        self.report(ERROR, message, form, **kw)

    def warning(self, message, form=None, **kw):
        self.report(WARNING, message, form, **kw)

    # Definitions

    def definitions_of(self, path, variation):
        found = []
        for index, part in enumerate(self.parts[path]):
            if part.prose or not part.applies(variation):
                continue
            form = part.form
            if head(form) in DEFINITIONS and len(form) >= 2 and isinstance(form[1], edn.Symbol):
                definition = Definition(str(form[1]), form, path, index,
                                        "definitions" in part.options, part.variations)
                if head(form) == "defn":
                    definition.arities = defn_arities(form)
                elif head(form) == "def" and len(form) == 3 and head(form[2]) == "fn":
                    definition.arities = defn_arities(form[2])
                found.append(definition)
        return found

    # Running the analysis

    def run(self):
        variations = [v.name for v in self.closure.variations] or [None]
        per_variation = {}
        for variation in variations:
            self.found = []
            self.analyze_variation(variation)
            per_variation[variation] = self.found
        return merge(per_variation, variations) + self.placeholders()

    def placeholders(self):
        """One warning for the steps of the script still to be written"""
        count = 0
        stack = [part.form for part in self.parts[self.script] if not part.prose]
        while stack:
            form = stack.pop()
            if isinstance(form, list):
                if head(form) == "TBD":
                    count += 1
                stack.extend(form)
        if not count:
            return []
        steps = "step is" if count == 1 else "steps are"
        return [Diagnostic(WARNING, f"{count} {steps} still to be written (TBD): a run "
                           "can't pass until they are", path=self.script)]

    def analyze_variation(self, variation):
        closure = self.closure
        self.calls_of = {}  # core function -> names its body refers to
        self.called_from_script = set()  # names the script refers to
        self.current_core = None
        core_paths = closure.load_order[:-1]
        core_defs = {}
        core_order = []
        for path in core_paths:
            for definition in self.definitions_of(path, None):
                if path in closure.imports and definition.name in core_defs and \
                        core_defs[definition.name].path not in closure.imports:
                    continue  # imports never override the chain
                core_defs[definition.name] = definition
                core_order.append(definition)
        script_defs = self.definitions_of(self.script, variation)
        section = [d for d in script_defs if d.in_section]
        later = [d for d in script_defs if not d.in_section]
        handles = set(closure.uuts)
        variation_symbols = {s for v in closure.variations for s in v.symbols}

        definitions = dict(core_defs)
        for definition in section + later:
            definitions[definition.name] = definition
        final = (self.builtins | set(core_defs) | {d.name for d in script_defs}
                 | handles | variation_symbols)

        self.shadowing(core_order, script_defs, core_defs)

        # Core files: eager def values see the builtins and the core
        # definitions loaded before them
        bound = set(self.builtins)
        self.core_free = {}  # core defn name -> [(symbol, its span)] it can't find
        for definition in core_order:
            names = Names(bound, final, definitions)
            self.definition(definition, names, core=True)
            bound.add(definition.name)

        # The script: the definitions section, then handles and variation
        # symbols, then its statements in order
        names = Names(bound, final, definitions)
        for definition in section:
            self.definition(definition, names)
            names.available.add(definition.name)
        names.available |= handles
        for v in closure.variations:
            if v.name == variation or variation is None:
                for symbol, value in zip(v.symbols, v.forms):
                    self.expression(value, names, locals_=frozenset(), eager=True)
        names.available |= variation_symbols

        seen_section = {id(d.form) for d in section}
        for index, part in enumerate(self.parts[self.script]):
            if part.prose or not part.applies(variation):
                continue
            form = part.form
            name = head(form)
            if name in DEFINITIONS:
                if id(form) in seen_section:
                    continue
                definition = next((d for d in later if d.form is form), None)
                if definition is not None:
                    self.definition(definition, names)
                    names.available.add(definition.name)
                else:
                    self.error(f"{name} needs a name: ({name} name ...)", form)
            elif name in DIRECTIVES:
                continue
            elif name == PRECONDITION:
                parsed = parse_precondition(form)
                if parsed is not None:
                    self.expression(parsed.check, names, frozenset(), eager=True)
                    if parsed.heal is not None:
                        self.expression(parsed.heal, names, frozenset(), eager=True)
            else:
                self.discarded(form)
                self.expression(form, names, frozenset(), eager=True, top=True)

        self.report_core_free(core_defs, names)

    def shadowing(self, core_order, script_defs, core_defs):
        for definition in core_order + script_defs:
            name = definition.name
            what = ("the block" if name in self.block_names
                    else "the special form" if name in self.special | KNOWN_FORMS
                    else "the builtin" if name in self.builtins else None)
            if what:
                self.warning(f"{name} shadows {what} {name}", definition.form[1],
                             parent=definition.form, index=1)
        for definition in script_defs:
            core = core_defs.get(definition.name)
            if core is not None and definition.name not in self.block_names:
                where = f"{core.path}"
                if core.span is not None:
                    where += f":{core.span.line}"
                self.warning(f"{definition.name} shadows the definition in {where}",
                             definition.form[1], parent=definition.form, index=1)

    def definition(self, definition, names, core=False):
        """Check one top-level def or defn"""
        form = definition.form
        kind = head(form)
        self.current_core = definition.name if core else None
        if kind == "def":
            if len(form) != 3:
                self.error("def takes a name and a value: (def name value)", form)
                return
            # core.rst files and the definitions section load before
            # anything runs: no block can be called yet
            self.loading = core or definition.in_section
            self.expression(form[2], names, frozenset(), eager=True, core=core)
            self.loading = False
        else:
            self.fn_body(form, names, frozenset(), defn=True, core=core)
        self.current_core = None

    def report_core_free(self, core_defs, names):
        """Names reachable core.rst functions use that nothing defines"""
        reachable = set()
        pending = list(self.called_from_script)
        while pending:
            name = pending.pop()
            if name in reachable or name not in core_defs:
                continue
            reachable.add(name)
            pending.extend(self.calls_of.get(name, ()))
        for name in sorted(reachable):
            for symbol, form, parent, index in self.core_free.get(name, ()):
                self.unknown(symbol, names.final, form, parent, index,
                             note=f" (used by {name}, which this script calls)")

    # Forms

    def expression(self, form, names, locals_, eager, top=False, core=False):
        """Check a form that is evaluated. `eager` forms run as they are
        reached; others (function bodies) run later, when everything is
        bound."""
        if isinstance(form, edn.Keyword):
            return
        if isinstance(form, edn.Symbol):
            self.symbol(form, names, locals_, eager, core)
            return
        if isinstance(form, dict):
            for k, v in form.items():
                self.expression(k, names, locals_, eager, core=core)
                self.expression(v, names, locals_, eager, core=core)
            return
        if isinstance(form, (edn.Vector, set)):
            for item in form:
                self.expression(item, names, locals_, eager, core=core)
            return
        if not isinstance(form, edn.List) or not form:
            return
        self.call(form, names, locals_, eager, top, core)

    def symbol(self, symbol, names, locals_, eager, core, parent=None, index=None):
        name = str(symbol)
        if name in locals_:
            return
        self.note_reference(name, core)
        if name in (names.available if eager else names.final):
            return
        if core and not eager:
            self.core_free.setdefault(self.current_core, []).append(
                (symbol, symbol, parent, index))
            return
        self.unknown(symbol, names, symbol, parent, index, eager=eager)

    def note_reference(self, name, core):
        """Record which functions the script (or a core function) refers to"""
        if core and self.current_core is not None:
            self.calls_of.setdefault(self.current_core, set()).add(name)
        elif not core:
            self.called_from_script.add(name)

    def unknown(self, symbol, names, form, parent=None, index=None, eager=False, note=""):
        name = str(symbol)
        final = names if isinstance(names, set) else names.final
        if eager and not isinstance(names, set) and name in final:
            definition = names.definitions.get(name)
            if definition is not None and definition.span is not None:
                where = definition.path if definition.path != self.script else "line"
                where = f"{where}:{definition.span.line}" if where != "line" else \
                    f"line {definition.span.line}"
                self.error(f"{name} is used before it is defined ({where}){note}",
                           form, parent=parent, index=index)
            else:
                self.error(f"{name} isn't bound yet here: UUT handles and variation "
                           "symbols are bound after the definitions section loads"
                           f"{note}", form, parent=parent, index=index)
            return
        candidates = final | self.block_names
        close = difflib.get_close_matches(name, candidates, 1, 0.75)
        hint = f"; did you mean {close[0]}?" if close else ""
        self.error(f"unknown name {name}{note}{hint}", form, parent=parent, index=index)

    def call(self, form, names, locals_, eager, top, core):
        first = form[0]
        if not isinstance(first, edn.Symbol):
            for i, item in enumerate(form):
                self.expression(item, names, locals_, eager, core=core)
            return
        name = str(first)
        rest = form[1:]

        def each(items, eager_=eager, locals__=locals_):
            for item in items:
                self.expression(item, names, locals__, eager_, core=core)

        if name in locals_:
            each(rest)
            return
        if name in REMOVED:
            self.error(REMOVED[name], first)
            return
        if name in ("def", "defn"):
            self.error(f"{name} is only allowed at the top level of a core.rst or a "
                       "script, not inside another form", first)
            return
        if name in DIRECTIVES or name == PRECONDITION:
            self.error(f"{name} is only allowed at the top level of a script", first)
            return
        if name == "quote":
            if len(form) != 2:
                self.error("quote takes one form: (quote form)", form)
            return
        if name == "if":
            if len(rest) not in (2, 3):
                self.error("if takes a test, a then and an optional else: "
                           "(if test then else)", form)
            each(rest)
            return
        if name in ("do", "quietly"):
            each(rest)
            return
        if name == "let":
            self.let(form, names, locals_, eager, core)
            return
        if name == "fn":
            self.fn_body(form, names, locals_, defn=False, core=core)
            return
        if name == "step":
            if not rest or not is_text(rest[0]):
                self.error('step takes a title string, then its body: (step "title" ...)',
                           form)
                each(rest)
            else:
                each(rest[1:])
            return
        if name == "try-ok?":
            if len(rest) != 1:
                self.error("try-ok? takes one form: (try-ok? form)", form)
            each(rest)
            return
        if name == "try":
            if len(rest) != 2:
                self.error("try takes a form and a default: (try form default)", form)
            each(rest)
            return
        if name.startswith(".") and len(name) > 1:
            if not rest:
                self.error(f"({name} obj ...) needs an object", form)
            each(rest)
            return

        defined = name in names.final or name in names.available
        definition = names.definitions.get(name)
        if name in self.block_names and not (definition and defined):
            self.block_call(form, names, locals_, eager, core)
            return
        if name in self.special and not defined:
            each(rest)  # a special form this analyzer doesn't know the shape of
            return

        self.symbol(first, names, locals_, eager, core, parent=form, index=0)
        if definition is not None and definition.arities is not None and \
                definition.arities and len(rest) not in definition.arities:
            counts = " or ".join(str(n) for n in sorted(definition.arities))
            plural = "" if definition.arities == {1} else "s"
            where = definition.path
            if definition.span is not None:
                where += f":{definition.span.line}"
            self.error(f"{name} takes {counts} argument{plural}, not {len(rest)} "
                       f"(defined in {where})", form)
        each(rest)

    def block_call(self, form, names, locals_, eager, core):
        name = str(form[0])
        self.note_reference(name, core)
        if eager and getattr(self, "loading", False):
            self.error(f"{name} can't be called here: core.rst files and the "
                       "definitions section load before any block can run. Define "
                       "the value after the definitions section, or as a function",
                       form)
            return
        block = None
        for candidate in all_blocks():
            if candidate.name() == name and candidate.check_syntax(*form[1:]):
                block = candidate
                break
        if block is None:
            usage = " or ".join(self.blocks[name].usage().splitlines())
            self.error(f"no form of {name} matches this call: see its usage, {usage}",
                       form)
            return
        if block.execute_forms is not None:
            return  # the block takes its arguments as written
        argument_names = block.argument_names(len(form) - 1)
        for i, (arg, param) in enumerate(zip(form[1:], argument_names), start=1):
            if param in block.quoted:
                continue
            if isinstance(arg, edn.Symbol) and not isinstance(arg, edn.Keyword):
                self.symbol(arg, names, locals_, eager, core, parent=form, index=i)
            else:
                self.expression(arg, names, locals_, eager, core=core)

    def let(self, form, names, locals_, eager, core):
        if len(form) < 2 or not isinstance(form[1], edn.Vector) or len(form[1]) % 2:
            self.error("let takes a vector of name value pairs, then its body: "
                       "(let [name value ...] body...)", form)
            return
        bound = set(locals_)
        bindings = form[1]
        for i in range(0, len(bindings), 2):
            target, value = bindings[i], bindings[i + 1]
            self.expression(value, names, frozenset(bound), eager, core=core)
            if not isinstance(target, edn.Symbol) or isinstance(target, edn.Keyword):
                self.error(f"let can only bind names, not {edn.writes(target)}",
                           target, parent=bindings, index=i)
            else:
                bound.add(str(target))
        for item in form[2:]:
            self.expression(item, names, frozenset(bound), eager, core=core)

    def fn_body(self, form, names, locals_, defn, core):
        """fn or defn: parameters are bound in the body, which runs later"""
        kind = "defn" if defn else "fn"
        rest = list(form[2:] if defn else form[1:])
        if defn and (len(form) < 2 or not isinstance(form[1], edn.Symbol)):
            self.error("defn needs a name: (defn name [params] body...)", form)
            return
        if not defn and rest and isinstance(rest[0], edn.Symbol):
            rest = rest[1:]
        if rest and isinstance(rest[0], edn.Vector):
            signatures = [rest]
        else:
            signatures = rest
        if not signatures:
            self.error(f"{kind} needs parameters: ({kind} {'name ' if defn else ''}"
                       "[params] body...)", form)
            return
        for signature in signatures:
            if not (isinstance(signature, list) and signature
                    and isinstance(signature[0], edn.Vector)):
                self.error(f"{kind} parameters must be a vector, e.g. [x y]",
                           signature if isinstance(signature, list) else form)
                continue
            params, *body = signature
            bound = set(locals_)
            for i, param in enumerate(params):
                if not isinstance(param, edn.Symbol) or isinstance(param, edn.Keyword):
                    self.error(f"parameters must be names, not {edn.writes(param)}",
                               param, parent=params, index=i)
                else:
                    bound.add(str(param))
            for item in body:
                self.expression(item, names, frozenset(bound), eager=False, core=core)

    def discarded(self, form):
        """Warn about a top-level step whose value is all it does"""
        if isinstance(form, edn.List) and form:
            name = head(form)
            if name is None or name not in self.builtins or name in EFFECTFUL:
                return
        message = (f"the value of {edn.writes(form)} is not used: a step only fails "
                   "through a block. Did you mean (Verify ...)?")
        self.warning(message, form)


def merge(per_variation, variations):
    """One list of diagnostics, each saying which variations it applies to
    when that isn't all of them"""
    merged, order = {}, []
    for variation in variations:
        for diagnostic in per_variation[variation]:
            key = diagnostic.key()
            if key not in merged:
                merged[key] = (diagnostic, [])
                order.append(key)
            if variation not in merged[key][1]:
                merged[key][1].append(variation)
    found = []
    for key in order:
        diagnostic, where = merged[key]
        if variations != [None] and len(where) < len(variations):
            diagnostic.variations = where
        found.append(diagnostic)
    return found


def analyze(closure, parsed=None):
    """The Diagnostics of a resolved closure (see the module docs).
    `parsed` maps paths to their document parts, if already parsed."""
    return Analyzer(closure, parsed).run()
