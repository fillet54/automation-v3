import importlib
import pkgutil

import automationv3.plugins

from . import edn


class BuildingBlock:
    """
    The 'BuildingBlock' of the automation framework. Registers as a function to
    be run during text execution.
    """

    def name(self):
        """Returns the name of the building block. The name is used
        as a first order lookup for the block"""
        return type(self).__name__

    def check_syntax(self, *args):
        """Returns True if this BuildingBlock can support the
        arguments and False otherwise"""
        return True

    def execute(self, *args):
        """Executes the block.

        Returns a BlockResult"""
        return BlockResult(False)

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
        src = edn.writes(edn.List([self.name(), *args]))
        return (
            "\n".join(
                [
                    ".. code-block:: clojure",
                    "",
                    *["  " + line for line in src.splitlines()],
                ]
            )
            + "\n\n"
        )

    def as_html(self, *args):
        """HTML for a step using this block, or None to use as_rst"""
        return None


def raw_html(html):
    """rst that embeds `html` as is"""
    body = "\n".join("   " + line for line in html.splitlines())
    return f".. raw:: html\n\n{body}\n\n"


class BuildingBlockInst:
    """Building block `instance` which packs block together with arguments

    This provides a mechanism to make a BuildingBlock
    more pythonic without breaking backwards compatibility.

    New blocks are free to implement either this or BuildingBlock.
    The framework will mostly be interfacing with blocks via this
    interface.
    """

    def __init__(self, block, args):
        self.block = block
        self.args = args

    def name(self):
        return self.block.name()

    def valid(self):
        return self.block.check_syntax(*self.args)

    def execute(self):
        return self.block.execute(*self.args)

    def __repr_rst__(self):
        return self.block.as_rst(*self.args)


class BlockResult(object):
    """
    The result of executing a BuildingBlock
    """

    def __init__(self, passed, stdout="", stderr=""):
        self.passed = passed
        self.stdout = stdout
        self.stderr = stderr

    def __bool__(self):
        return self.passed

    def __str__(self):
        result = "PASS" if self.passed else "FAIL"
        return f"<BlockResult: {result}, {self.stdout}, {self.stderr}>"


def all_blocks():
    """An instance of every BuildingBlock subclass loaded so far"""
    found, stack = [], list(BuildingBlock.__subclasses__())
    while stack:
        cls = stack.pop(0)
        stack.extend(cls.__subclasses__())
        found.append(cls())
    return found


def find_block(form):
    """The block (with its arguments) that handles a step form, or None"""
    name, *args = form

    for block in all_blocks():
        if block.name() == name and block.check_syntax(*args):
            return BuildingBlockInst(block, args)


def iter_namespace(ns_pkg):
    return pkgutil.iter_modules(ns_pkg.__path__, ns_pkg.__name__ + ".")


# Importing every plugin registers its blocks
discovered_plugins = {
    name: importlib.import_module(name)
    for finder, name, ispkg in iter_namespace(automationv3.plugins)
}
