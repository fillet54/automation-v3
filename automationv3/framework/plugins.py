"""Automatic plugin discovery and registration of default Lisp functions.

All packages under ``automationv3.plugins`` and installed entry points in
the ``automationv3.plugins`` group load automatically. A plugin may expose
``register(registry)`` to add Lisp functions with ``registry.function``.
Blocks, UUTs and environments are still discovered through their subclasses.
"""

import importlib
import inspect
import pkgutil
import threading
from dataclasses import dataclass
from importlib.metadata import entry_points

import automationv3.plugins

from . import edn, lisp
from .language import DIRECTIVES, PRECONDITION


@dataclass(frozen=True)
class LispFunction:
    name: str
    function: object
    plugin: str

    @property
    def doc(self):
        return inspect.getdoc(self.function) or ""


_functions = {}
_loaded = False
_loading = False
_lock = threading.RLock()

# Execution forms may register later, when steps.py is imported.
RESERVED = {"step", "try", "try-ok?", "quietly", "defblock", "passes?",
            PRECONDITION} | DIRECTIVES


class PluginRegistry:
    """The registration interface passed to one plugin's register hook.

    ``function(name, fn)`` exposes a callable to scripts and static analysis.
    Duplicate names, builtins, special forms and block names are rejected.
    Registering the same function again for the same plugin is harmless.
    Scripts can shadow defaults in their own scope with def or defn.
    """

    def __init__(self, plugin):
        self.plugin = plugin

    def function(self, name, fn):
        if not isinstance(name, str):
            raise TypeError("a Lisp function name must be a string")
        try:
            symbol = edn.read(name)
        except Exception as e:
            raise ValueError(f"invalid Lisp function name {name!r}") from e
        if (not isinstance(symbol, edn.Symbol) or isinstance(symbol, edn.Keyword)
                or str(symbol) != name):
            raise ValueError(f"invalid Lisp function name {name!r}")
        if not callable(fn):
            raise TypeError(f"{name}: a Lisp function must be callable")
        with _lock:
            previous = _functions.get(name)
            if previous is not None:
                if previous.plugin == self.plugin and previous.function is fn:
                    return fn
                raise ValueError(f"Lisp function {name} is already registered by "
                                 f"{previous.plugin}; cannot register it for {self.plugin}")
            from .block import block_names
            if name in lisp.global_env or name in RESERVED or \
                    name in lisp.special_forms or name in block_names():
                raise ValueError(f"Lisp function {name} conflicts with a builtin, "
                                 "special form or block")
            _functions[name] = LispFunction(name, fn, self.plugin)
            # String keys also match both spellings of namespaced Symbols:
            # Symbol("f", "plugin") from EDN and Symbol("plugin/f") in tools.
            lisp.global_env[name] = fn
        return fn


def registered_functions():
    """Registered Lisp functions, with their plugin and documentation."""
    load_plugins()
    return tuple(_functions[name] for name in sorted(_functions))


def load_plugins():
    """Load every bundled and installed plugin once, core first.

    An installed entry point can name a module with register(registry), or
    the registration function itself. Imports are deferred until discovery
    or execution so abstract contracts can be imported without cycles.
    """
    global _loaded, _loading
    with _lock:
        if _loaded or _loading:
            return
        _loading = True
        before_functions, before_env = dict(_functions), dict(lisp.global_env)
        try:
            modules = sorted(pkgutil.iter_modules(automationv3.plugins.__path__,
                             automationv3.plugins.__name__ + "."),
                             key=lambda m: (m.name != "automationv3.plugins.core", m.name))
            for module in modules:
                plugin = importlib.import_module(module.name)
                register = getattr(plugin, "register", None)
                if register is not None:
                    register(PluginRegistry(module.name))
            for entry in sorted(entry_points(group="automationv3.plugins"),
                                key=lambda e: e.name):
                plugin = entry.load()
                register = plugin if callable(plugin) else getattr(plugin, "register", None)
                if register is None:
                    raise TypeError(f"Plugin {entry.name} needs register(registry)")
                register(PluginRegistry(entry.name))
            # A plugin loaded later may introduce a block with an earlier
            # function's name. Check the completed set as well.
            from .block import block_names
            conflicts = set(_functions) & block_names()
            if conflicts:
                raise ValueError("Lisp functions conflict with blocks: "
                                 + ", ".join(sorted(conflicts)))
            _loaded = True
        except Exception:
            _functions.clear()
            _functions.update(before_functions)
            lisp.global_env.clear()
            lisp.global_env.update(before_env)
            raise
        finally:
            _loading = False
