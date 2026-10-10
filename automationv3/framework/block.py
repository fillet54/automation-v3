"""BuildingBlocks: the steps scripts are written in

A BuildingBlock subclass is a step scripts can call by its name, e.g.
(Verify x = 1). Plugins in `automationv3.plugins` define them; every
plugin module is imported when this module loads, which registers its
blocks.

Every block is one of three kinds, which decides what a call of it
gives the code around it and how it reports:

- an action does something to the system (start it, set a reading).
  A call gives back whatever `execute` returned (usually nil).
- an assertion checks something. A call gives back true or false, and
  a false one fails the step (unless suppressed with try-ok? or try).
- a value reads something. A call gives back the value; reports show
  it quietly, with what it returned.

Only blocks fail steps: an action or a value fails by raising (or by
returning a failed BlockResult), an assertion by coming out false.

A call is resolved to a block by name and `check_syntax`, which sees
the call's arguments evaluated, so blocks of one name can each take a
type of their own (e.g. a plugin's Read takes its own kind of ref). The
arguments are evaluated once, before the blocks are asked, and the
block found gets those values. Blocks that take their arguments as
written (`execute_forms`, or `quoted` parameters) are asked
`check_syntax_forms` instead. The first block that accepts a call runs
it; for a block that sets `require_unique`, every block of the name is
asked, and more than one accepting is an error. An `abstract` block
only documents a name (its usage and docs) for plugins to implement:
it is never asked.
"""

import importlib
import inspect
import pkgutil
from dataclasses import dataclass

import automationv3.plugins

from . import edn, refs  # noqa: F401  refs adds its builtins
from .context import calling, evaluate


ACTION = "action"
ASSERTION = "assertion"
VALUE = "value"
PLACEHOLDER = "placeholder"  # a step not written yet: see plugins/core/tbd.py
KINDS = (ACTION, ASSERTION, VALUE, PLACEHOLDER)


@dataclass
class BlockResult:
    """The result of executing a BuildingBlock: true if it passed.

    `value` is what a call of the block gives the code around it. A
    result that didn't pass is an `error` if the block raised (or
    couldn't run at all) rather than coming out false."""

    passed: bool
    stdout: str = ""
    stderr: str = ""
    value: object = None
    error: bool = False

    def __bool__(self):
        return bool(self.passed)


class BuildingBlock:
    """A step scripts can call by name.

    `kind` is ACTION (the default), ASSERTION or VALUE; see the module
    documentation for what each means.

    A step's arguments reach `execute` evaluated, like a function call:
    symbols, calls, and values inside maps and vectors are evaluated in
    the running script (definitions, variation symbols, UUT handles).
    Parameters named in `quoted` get their argument as written instead,
    e.g. Verify's operator. A block that gives meaning to all its forms,
    e.g. treating bare symbols as names, implements `execute_forms`
    instead and gets every argument exactly as written; it never
    evaluates them itself. `check_syntax`, `as_rst` and `as_html` always
    see the forms as written; `context.written_args()` gives them to a
    running `execute` too.

    `execute` returns a BlockResult or a plain value: for an assertion,
    a plain value passes if it is truthy; for an action or a value, a
    plain value passes and is what the call gives back.

    A block documents itself: `usage` says how scripts call it, and the
    class docstring, written in reStructuredText, says what it does.
    The documentation site renders both for every block.
    """

    kind = ACTION
    quoted = frozenset()  # parameters of `execute` taken as written
    # True: a call must be accepted by exactly one block of this name
    require_unique = False
    # True (set on the class itself, not inherited): this block only
    # documents a name for plugins to implement, and is never called
    abstract = False

    def name(self):
        """The name scripts call the block by"""
        return type(self).__name__

    def usage(self):
        """How scripts call the block, one call per line, e.g.::

            (Verify actual op expected)
            (Verify value)

        By default, the name and the parameters of `execute` (or
        `execute_forms`): `name?` for an optional one, `name...` for the
        rest. Override it when the calls take a particular shape.
        """
        params = inspect.signature(self.execute_forms or self.execute).parameters
        words = [self.name()]
        for param in params.values():
            word = param.name.replace("_", "-")
            if param.kind is param.VAR_POSITIONAL:
                word += "..."
            elif param.default is not param.empty:
                word += "?"
            words.append(word)
        return f"({' '.join(words)})"

    def doc(self):
        """The block's documentation, in reStructuredText: its class
        docstring, or "" if it has none of its own"""
        return inspect.cleandoc(type(self).__dict__.get("__doc__") or "")

    def check_syntax(self, *values):
        """True if the block accepts a call with these arguments,
        evaluated. Only asked of blocks that take their arguments
        evaluated; see check_syntax_forms."""
        return True

    # Defined by blocks that take their arguments as written (with
    # `execute_forms` or `quoted` parameters), which are asked this
    # instead of check_syntax, with the forms as written:
    #     def check_syntax_forms(self, *forms): -> bool
    check_syntax_forms = None

    def takes_forms(self):
        """True if the block is matched (and run) on its forms as written"""
        return (self.check_syntax_forms is not None or self.execute_forms is not None
                or bool(self.quoted))

    def accepts_forms(self, *forms):
        """check_syntax_forms, for a block that takes forms (an older one
        that only defines check_syntax is asked that, with the forms)"""
        if self.check_syntax_forms is not None:
            return self.check_syntax_forms(*forms)
        return self.check_syntax(*forms)

    def accepts_count(self, count):
        """True if `execute` can take `count` arguments"""
        try:
            inspect.signature(self.execute).bind(*([None] * count))
            return True
        except TypeError:
            return False

    def execute(self, *args):
        """Run the block with its arguments evaluated (except `quoted`
        ones). Returns a BlockResult or a plain value."""
        return BlockResult(False)

    def result(self, returned):
        """What `execute` (or `execute_forms`) returned, as a BlockResult
        whose `value` is what the call gives back"""
        if isinstance(returned, BlockResult):
            if self.kind == ASSERTION:
                returned.value = bool(returned.passed)
            return returned
        if self.kind == ASSERTION:
            return BlockResult(bool(returned), value=bool(returned))
        return BlockResult(True, value=returned)

    def argument_names(self, count):
        """The parameter of `execute` each of `count` arguments binds"""
        params = list(inspect.signature(self.execute).parameters.values())
        names = []
        for i in range(count):
            if i < len(params) and params[i].kind is not params[i].VAR_POSITIONAL:
                names.append(params[i].name)
            else:
                rest = [p for p in params if p.kind is p.VAR_POSITIONAL]
                names.append(rest[0].name if rest else None)
        return names

    # Defined by blocks that take their arguments unevaluated:
    #     def execute_forms(self, *forms): ...
    execute_forms = None

    # Defined by such blocks when they evaluate some of their forms
    # themselves (e.g. Wait, again and again), so static analysis checks
    # those forms like any other code:
    #     def evaluated_forms(self, *forms): -> [form, ...]
    evaluated_forms = None

    def as_rst(self, *args):
        """How a step using this block reads in a rendered script.

        Blocks render themselves so a script reads well, e.g. a
        configuration as a table instead of a large edn structure.
        Override this to write reStructuredText, or as_html to write
        HTML. By default the step is shown as code.
        """
        html = self.as_html(*args)
        if html is not None:
            return raw_html(html)
        return code_block(edn.writes(edn.List([edn.Symbol(self.name()), *args])))

    def as_html(self, *args):
        """HTML for a step using this block, or None to use as_rst"""
        return None


def raw_html(html):
    """rst that embeds `html` as is"""
    body = "\n".join("   " + line for line in html.splitlines())
    return f".. raw:: html\n\n{body}\n\n"


def code_block(source):
    """rst that shows edn `source` as code"""
    body = "\n".join("  " + line for line in source.splitlines())
    return f".. code-block:: clojure\n\n{body}\n\n"


class BuildingBlockInst:
    """A block found for a step, with the step's arguments as written, and
    their values if they were evaluated to find it"""

    def __init__(self, block, args, values=None):
        self.block = block
        self.args = args
        self.values = values

    def evaluated_args(self, env=None):
        """The arguments `execute` gets: evaluated in `env`, except those
        for `quoted` parameters"""
        names = self.block.argument_names(len(self.args))
        return [arg if name in self.block.quoted else evaluate(arg, env)
                for arg, name in zip(self.args, names)]

    def execute(self, env=None):
        """Run the block: forms as written to execute_forms if the block
        has it, otherwise evaluated (in `env`) to execute. Returns a
        BlockResult (see BuildingBlock.result)."""
        with calling(self.args):
            if self.block.execute_forms is not None:
                returned = self.block.execute_forms(*self.args)
            elif self.values is not None and not self.block.takes_forms():
                returned = self.block.execute(*self.values)
            else:
                returned = self.block.execute(*self.evaluated_args(env))
        return self.block.result(returned)

    def __repr_rst__(self):
        return self.block.as_rst(*self.args)


_instances = {}


def all_blocks():
    """An instance of every BuildingBlock subclass loaded so far"""
    found, stack = [], list(BuildingBlock.__subclasses__())
    while stack:
        cls = stack.pop(0)
        stack.extend(cls.__subclasses__())
        if cls not in _instances:
            _instances[cls] = cls()
        found.append(_instances[cls])
    return found


def is_abstract(block):
    return type(block).__dict__.get("abstract", False)


def block_names():
    return {block.name() for block in all_blocks()}


def candidates(name):
    """The blocks a call of `name` may resolve to, in the order asked"""
    return [b for b in all_blocks() if b.name() == name and not is_abstract(b)]


def documented(name):
    """The block documenting a name: its abstract block if it has one"""
    found = [b for b in all_blocks() if b.name() == name]
    return next((b for b in found if is_abstract(b)), found[0] if found else None)


class NoBlock(ValueError):
    """No block accepts a call"""


class AmbiguousBlock(ValueError):
    """More than one block accepts a call of a name that must resolve to one"""


def _type_names(values):
    return ", ".join(type(v).__name__ for v in values) or "no arguments"


def _block_id(block):
    return f"{type(block).__module__.rsplit('.', 1)[-1]}.{type(block).__qualname__}"


def resolve(form, env=None):
    """The block (with its arguments, and their values if it takes them
    evaluated) that runs a call. Raises NoBlock or AmbiguousBlock."""
    name, *forms = form
    found = candidates(name)
    unique = any(block.require_unique for block in found)
    values, matches = None, []
    for block in found:
        if block.takes_forms():
            accepted = block.accepts_forms(*forms)
        else:
            if values is None:
                values = [evaluate(f, env) for f in forms]
            accepted = block.check_syntax(*values)
        if accepted:
            matches.append(block)
            if not unique:
                break
    if not matches:
        doc = documented(name)
        usage = " or ".join(doc.usage().splitlines()) if doc else name
        if not found:
            raise NoBlock(f"no plugin implements {name}: see its usage, {usage}")
        given = f" given {_type_names(values)}" if values is not None else ""
        raise NoBlock(f"no form of {name} accepts {edn.writes(edn.List(form))}"
                      f"{given}: see its usage, {usage}")
    if len(matches) > 1:
        raise AmbiguousBlock(
            f"{name} is accepted by {len(matches)} blocks "
            f"({', '.join(_block_id(b) for b in matches)}), given "
            f"{_type_names(values or [])}: only one may accept a call of {name}")
    block = matches[0]
    return BuildingBlockInst(block, forms, None if block.takes_forms() else values)


def find_block(form):
    """The block a call is likely to resolve to, judged on its forms alone
    (no evaluating): for rendering a step. None if no block fits."""
    name, *args = form
    for block in candidates(name):
        if block.takes_forms():
            if block.accepts_forms(*args):
                return BuildingBlockInst(block, args)
        elif block.accepts_count(len(args)):
            return BuildingBlockInst(block, args)
    doc = documented(name)
    if doc is not None and doc.accepts_count(len(args)):
        return BuildingBlockInst(doc, args)
    return None


def load_plugins():
    """Import every plugin module, which registers its blocks"""
    for module in pkgutil.iter_modules(automationv3.plugins.__path__,
                                       automationv3.plugins.__name__ + "."):
        importlib.import_module(module.name)


load_plugins()
