"""Automatic plugin discovery and registration of default Lisp functions.

All packages under ``automationv3.plugins`` and installed entry points in
the ``automationv3.plugins`` group load automatically. A plugin may expose
``register(registry)`` to add Lisp functions with ``registry.function``,
and what documents render with (see documents/): directives and roles
(``registry.directive``, ``registry.role``), snippet filters and folders
(``registry.filter``, ``registry.snippets``), and CSS and LaTeX to style
what they write (``registry.css``, ``registry.latex``). Blocks, UUTs and
environments are still discovered through their subclasses; a block
renders its own steps and results (BuildingBlock.as_rst, as_result_rst).
"""

import importlib
import inspect
import pkgutil
import threading
from contextlib import contextmanager
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


class PluginLoadError(RuntimeError):
    """A plugin could not be loaded; `plugin` names it (None when loaded
    plugins conflict with each other)"""

    def __init__(self, plugin, message):
        super().__init__(message)
        self.plugin = plugin


_functions = {}
_rendering = {"directive": {}, "role": {}, "filter": {}, "snippet": {}}  # name -> plugin
_directives = {}   # name -> (resolver, option_spec, arguments)
_roles = {}        # name -> value
_filters = {}      # name -> fn
_snippet_folders = []  # [Path]
_rendering_backend = None  # registered by documents/registry.py
_backend_baseline = None  # its snapshot before plugins' items were replayed into it
_styles = {"css": [], "latex": []}  # (plugin, text)
_versions = {}  # plugin -> its version
_loaded = False
_loading = False
_error = None  # the PluginLoadError of a failed load, raised again when asked
_lock = threading.RLock()


def set_rendering_registry(backend):
    """Attach the document rendering registry (called by documents/).
    Any directives, roles, filters and snippet folders plugins registered
    before documents/ was imported are replayed into `backend`."""
    global _rendering_backend, _backend_baseline
    with _lock:
        _rendering_backend = backend
        _backend_baseline = None
        if backend is None:
            return
        # every name first, so a clash registers nothing
        for kind, names in (("directive", _directives), ("role", _roles),
                            ("filter", _filters)):
            for name in names:
                if name in backend.builtins(kind):
                    raise ValueError(f"the {kind} {name} is a built-in one")
        _backend_baseline = backend.snapshot()
        for name, (resolver, option_spec, arguments) in _directives.items():
            backend.register_directive(name, resolver, option_spec, arguments)
        for name, value in _roles.items():
            backend.register_role(name, value)
        for name, fn in _filters.items():
            backend.register_filter(name, fn)
        for folder in _snippet_folders:
            backend.register_snippets(folder)

# Execution forms may register later, when steps.py is imported.
RESERVED = {"step", "try", "try-ok?", "quietly", PRECONDITION} | DIRECTIVES


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

    # What documents render with

    def _claim(self, kind, name, taken):
        with _lock:
            owner = _rendering[kind].get(name)
            if owner is not None and owner != self.plugin:
                raise ValueError(f"the {kind} {name} is already registered by {owner}; "
                                 f"cannot register it for {self.plugin}")
            if owner is None and name in taken:
                raise ValueError(f"the {kind} {name} is a built-in one")
            _rendering[kind][name] = self.plugin

    def directive(self, name, resolver, option_spec=None, arguments=False):
        """A directive documents can use: ``resolver(context, options)``
        writes its rst, from context.data (the report) and context.run
        (see documents/core.py); with `arguments`, its one argument is
        options["argument"]"""
        builtins = _rendering_backend.builtins("directive") if _rendering_backend else ()
        self._claim("directive", name, builtins)
        _directives[name] = (resolver, option_spec, arguments)
        if _rendering_backend is not None:
            _rendering_backend.register_directive(name, resolver, option_spec, arguments)
        return resolver

    def role(self, name, value):
        """A role documents can use: ``:name:`what``` is ``value(context,
        what)``, inline rst"""
        builtins = _rendering_backend.builtins("role") if _rendering_backend else ()
        self._claim("role", name, builtins)
        _roles[name] = value
        if _rendering_backend is not None:
            _rendering_backend.register_role(name, value)
        return value

    def filter(self, name, fn):
        """A filter every snippet can use"""
        builtins = _rendering_backend.builtins("filter") if _rendering_backend else ()
        self._claim("filter", name, builtins)
        _filters[name] = fn
        if _rendering_backend is not None:
            _rendering_backend.register_filter(name, fn)
        return fn

    def snippets(self, folder):
        """A folder of snippets (by name, e.g. report/results.rst): new
        ones for the plugin's directives, or the built-in ones overridden.
        Two plugins can't provide the same snippet."""
        from pathlib import Path

        folder = Path(folder)
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                self._claim("snippet", path.relative_to(folder).as_posix(), ())
        _snippet_folders.append(folder)
        if _rendering_backend is not None:
            _rendering_backend.register_snippets(folder)

    def css(self, text):
        """CSS for what the plugin's directives and blocks write: on live
        pages and in a frozen report's site"""
        _styles["css"].append((self.plugin, text))

    def latex(self, text):
        """LaTeX for the PDF's preamble: e.g. \\DUroleverdict-... commands
        or sphinxclass... environments for the plugin's classes"""
        _styles["latex"].append((self.plugin, text))


def plugin_css():
    load_plugins()
    return "\n".join(f"/* {plugin} */\n{text}" for plugin, text in _styles["css"])


def plugin_latex():
    load_plugins()
    return "\n".join(f"% {plugin}\n{text}" for plugin, text in _styles["latex"])


def plugin_versions():
    """plugin -> version, for every plugin loaded"""
    load_plugins()
    return dict(sorted(_versions.items()))


def registered_functions():
    """Registered Lisp functions, with their plugin and documentation."""
    load_plugins()
    return tuple(_functions[name] for name in sorted(_functions))


def load_plugins():
    """Load every bundled and installed plugin once, core first.

    An installed entry point can name a module with register(registry), or
    the registration function itself. Imports are deferred until discovery
    or execution so abstract contracts can be imported without cycles.

    A plugin that fails stops the load with a PluginLoadError naming it,
    and no plugin's functions are kept. The failure is remembered: asking
    again raises the same error rather than loading again, so the program
    reports it once at startup (see cli.main) and has to be restarted
    once the plugin is fixed.
    """
    global _loaded, _loading, _error
    with _lock:
        if _error is not None:
            raise _error
        if _loaded or _loading:
            return
        _loading = True
        before_functions, before_env = dict(_functions), dict(lisp.global_env)
        before_rendering = (
            {k: dict(v) for k, v in _rendering.items()},
            dict(_directives), dict(_roles), dict(_filters),
            list(_snippet_folders),
            {k: list(v) for k, v in _styles.items()},
            _rendering_backend.snapshot() if _rendering_backend is not None else None,
        )
        try:
            modules = sorted(pkgutil.iter_modules(automationv3.plugins.__path__,
                             automationv3.plugins.__name__ + "."),
                             key=lambda m: (m.name != "automationv3.plugins.core", m.name))
            for module in modules:
                with _loading_plugin(module.name):
                    plugin = importlib.import_module(module.name)
                    _versions[module.name] = bundled_version()
                    register = getattr(plugin, "register", None)
                    if register is not None:
                        register(PluginRegistry(module.name))
            for entry in sorted(entry_points(group="automationv3.plugins"),
                                key=lambda e: e.name):
                with _loading_plugin(entry.name):
                    plugin = entry.load()
                    dist = getattr(entry, "dist", None)
                    _versions[entry.name] = getattr(dist, "version", None) or "unknown"
                    register = plugin if callable(plugin) else \
                        getattr(plugin, "register", None)
                    if register is None:
                        raise TypeError("it needs register(registry)")
                    register(PluginRegistry(entry.name))
            # A plugin loaded later may introduce a block with an earlier
            # function's name. Check the completed set as well.
            from .block import block_names
            conflicts = set(_functions) & block_names()
            if conflicts:
                raise PluginLoadError(None, "Lisp functions conflict with blocks: "
                                      + ", ".join(sorted(conflicts)))
            _loaded = True
        except PluginLoadError as e:
            _functions.clear()
            _functions.update(before_functions)
            lisp.global_env.clear()
            lisp.global_env.update(before_env)
            forget_rendering(before_rendering)
            _error = e
            raise
        finally:
            _loading = False


def forget_rendering(before):
    """Undo what plugins registered for documents since `before`"""
    names, directives, roles, filters, folders, styles, backend_snap = before
    _rendering.clear()
    _rendering.update(names)
    _directives.clear()
    _directives.update(directives)
    _roles.clear()
    _roles.update(roles)
    _filters.clear()
    _filters.update(filters)
    _snippet_folders[:] = folders
    for kind, texts in styles.items():
        _styles[kind][:] = texts
    if backend_snap is None:  # documents/ came in during the load
        backend_snap = _backend_baseline
    if _rendering_backend is not None and backend_snap is not None:
        _rendering_backend.restore(backend_snap)


def bundled_version():
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version("automation-v3")
    except PackageNotFoundError:
        return "unknown"


@contextmanager
def _loading_plugin(name):
    try:
        yield
    except Exception as e:
        raise PluginLoadError(
            name, f"Plugin {name} failed to load: {type(e).__name__}: {e}") from e
