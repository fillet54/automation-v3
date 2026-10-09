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
"""

import importlib
import inspect
import pkgutil
from dataclasses import dataclass

import automationv3.plugins

from . import edn
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

    def check_syntax(self, *args):
        """True if the block accepts these arguments"""
        return True

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
    """A block found for a step, with the step's arguments as written"""

    def __init__(self, block, args):
        self.block = block
        self.args = args

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


def block_names():
    return {block.name() for block in all_blocks()}


def find_block(form):
    """The block (with its arguments) that handles a step form, or None"""
    name, *args = form
    for block in all_blocks():
        if block.name() == name and block.check_syntax(*args):
            return BuildingBlockInst(block, args)
    return None


def load_plugins():
    """Import every plugin module, which registers its blocks"""
    for module in pkgutil.iter_modules(automationv3.plugins.__path__,
                                       automationv3.plugins.__name__ + "."):
        importlib.import_module(module.name)


load_plugins()
