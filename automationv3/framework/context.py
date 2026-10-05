"""What a running step can reach

While a script runs, BuildingBlocks can look up the run's bindings (e.g.
a UUT handle by name, a variation symbol, a core.rvt definition) and
evaluate their arguments, which they receive unevaluated.
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


def evaluate(form):
    """Evaluate a block argument, including inside maps and vectors.

    Keywords and literals stay as they are; symbols and lists are
    evaluated as Lisp in the running script's environment.
    """
    env = current_env()
    if isinstance(form, dict):
        return edn.Map({evaluate(k): evaluate(v) for k, v in form.items()})
    if isinstance(form, edn.Vector):
        return edn.Vector(evaluate(item) for item in form)
    return lisp.eval(form, env)
