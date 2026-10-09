"""What a running step can reach

While a script runs, BuildingBlocks can look up the run's bindings (e.g.
a UUT handle by name, a variation symbol, a core.rst definition), see
the arguments of the call they are running as written
(`written_args`), e.g. to describe them in their output, and register
cleanups (`add_cleanup`) to run once the script ends, however it ends.
"""

import contextvars
from contextlib import contextmanager

from . import edn, lisp

_env = contextvars.ContextVar("env", default=None)


@contextmanager
def running(env):
    """Make `env` the current run's environment for the duration"""
    token = _env.set(env)
    try:
        yield env
    finally:
        _env.reset(token)


def current_env():
    env = _env.get()
    if env is None:
        raise RuntimeError("No script is running")
    return env


def lookup(name):
    """The value bound to `name` in the running script"""
    return current_env()[edn.Symbol(name)]


def evaluate(form, env=None):
    """Evaluate a form as Lisp in `env` (by default the running script's)"""
    return lisp.eval(form, env if env is not None else current_env())


_args = contextvars.ContextVar("args", default=())


@contextmanager
def calling(args):
    """Make `args` (forms as written) the running call's for the duration"""
    token = _args.set(tuple(args))
    try:
        yield
    finally:
        _args.reset(token)


def written_args():
    """The arguments of the block call running, as written"""
    return _args.get()


_cleanups = contextvars.ContextVar("cleanups", default=None)


@contextmanager
def cleanups():
    """Collect the cleanups registered for the duration: yields them, as
    key -> (description, fn), in the order registered"""
    registered = {}
    token = _cleanups.set(registered)
    try:
        yield registered
    finally:
        _cleanups.reset(token)


def add_cleanup(key, description, fn):
    """Have `fn()` run when the script ends, pass or fail. A key already
    registered keeps its first cleanup."""
    registered = _cleanups.get()
    if registered is None:
        raise RuntimeError("Cleanups can only be registered while a script runs")
    registered.setdefault(key, (description, fn))


def drop_cleanup(key):
    """Forget a cleanup, e.g. because the script did it itself"""
    registered = _cleanups.get()
    if registered is not None:
        registered.pop(key, None)
