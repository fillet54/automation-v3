"""BuildingBlocks: the steps scripts are written in

A BuildingBlock subclass is a step scripts can call by its name, e.g.
(Verify x = 1). Plugins in `automationv3.plugins` define them; every
plugin module is imported when this module loads, which registers its
blocks.
"""

import importlib
import pkgutil
from dataclasses import dataclass

import automationv3.plugins

from . import edn
from .context import evaluate


@dataclass
class BlockResult:
    """The result of executing a BuildingBlock: true if it passed"""

    passed: bool
    stdout: str = ""
    stderr: str = ""

    def __bool__(self):
        return bool(self.passed)


class BuildingBlock:
    """A step scripts can call by name.

    A step's arguments reach `execute` evaluated, like a function call:
    symbols, calls, and values inside maps and vectors are evaluated in
    the running script (definitions, variation symbols, UUT handles). A
    block that gives meaning to the forms themselves, e.g. treating bare
    symbols as names, implements `execute_forms` instead and gets the
    arguments exactly as written. `check_syntax`, `as_rst` and `as_html`
    always see the forms as written.
    """

    def name(self):
        """The name scripts call the block by"""
        return type(self).__name__

    def check_syntax(self, *args):
        """True if the block accepts these arguments"""
        return True

    def execute(self, *args):
        """Run the block with its arguments evaluated. Returns a BlockResult."""
        return BlockResult(False)

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

    def execute(self, env=None):
        """Run the block: forms as written to execute_forms if the block
        has it, otherwise evaluated (in `env`) to execute"""
        if self.block.execute_forms is not None:
            return self.block.execute_forms(*self.args)
        return self.block.execute(*[evaluate(arg, env) for arg in self.args])

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
